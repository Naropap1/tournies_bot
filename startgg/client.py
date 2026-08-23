"""
Async GraphQL client for the Start.gg API.

Provides rate-limited, authenticated access to Start.gg GraphQL endpoints
for retrieving tournaments, events, entrants, sets, reporting results,
and updating seeding.
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import TracebackType
from typing import Any

import aiohttp

from config import (
    STARTGG_API_URL,
    STARTGG_RATE_LIMIT,
    STARTGG_RATE_WINDOW,
    STARTGG_TOKEN,
)

logger = logging.getLogger(__name__)


class StartGGError(Exception):
    """Base exception for Start.gg API client errors."""


class StartGGHTTPError(StartGGError):
    """Raised when an HTTP error status is returned by the Start.gg API."""

    def __init__(self, message: str, status_code: int, response_body: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class StartGGGraphQLError(StartGGError):
    """Raised when GraphQL errors are returned in the response."""

    def __init__(self, message: str, errors: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.errors = errors


class StartGGClient:
    """
    Async client for querying and mutating data via the Start.gg GraphQL API.

    Handles authentication, lazy session initialization, request rate-limiting,
    and structured error handling for GraphQL queries and mutations.
    """

    def __init__(self, token: str | None = None) -> None:
        """
        Initialize the Start.gg client.

        Args:
            token: Optional API token. If omitted, uses STARTGG_TOKEN from config.
        """
        self._session: aiohttp.ClientSession | None = None
        self._request_times: list[float] = []
        self._token: str = token if token is not None else STARTGG_TOKEN
        self._api_url: str = STARTGG_API_URL

        if not self._token:
            logger.warning(
                "STARTGG_TOKEN is empty. Read-only queries may be attempted, "
                "but authenticated queries/mutations will fail."
            )

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """
        Lazily create and return the aiohttp ClientSession with auth headers.

        Returns:
            An active aiohttp.ClientSession instance.
        """
        if self._session is None or self._session.closed:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"

            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def _rate_limit(self) -> None:
        """
        Enforce rate limits on outgoing requests.

        If the rate limit threshold (default 80 requests / 60 seconds) is reached,
        sleeps until the oldest recorded request rolls out of the sliding window.
        """
        now = time.monotonic()
        # Keep only timestamps within the active sliding window
        self._request_times = [
            t for t in self._request_times if now - t < STARTGG_RATE_WINDOW
        ]

        if len(self._request_times) >= STARTGG_RATE_LIMIT:
            oldest = self._request_times[0]
            sleep_time = (oldest + STARTGG_RATE_WINDOW) - now
            if sleep_time > 0:
                logger.warning(
                    "Start.gg rate limit reached (%d requests in %ds). Sleeping for %.2fs.",
                    STARTGG_RATE_LIMIT,
                    STARTGG_RATE_WINDOW,
                    sleep_time,
                )
                await asyncio.sleep(sleep_time)
                now = time.monotonic()
                self._request_times = [
                    t for t in self._request_times if now - t < STARTGG_RATE_WINDOW
                ]

        self._request_times.append(time.monotonic())

    async def query(
        self, gql: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Execute a GraphQL query or mutation against Start.gg.

        Args:
            gql: GraphQL query or mutation string.
            variables: Optional mapping of query variables.

        Returns:
            The 'data' dictionary from the GraphQL response.

        Raises:
            StartGGHTTPError: If the HTTP response status is not 200.
            StartGGGraphQLError: If GraphQL execution errors are returned.
        """
        await self._rate_limit()
        session = await self._ensure_session()

        payload: dict[str, Any] = {
            "query": gql,
            "variables": variables or {},
        }

        async with session.post(self._api_url, json=payload) as response:
            text = await response.text()

            if response.status != 200:
                logger.error(
                    "Start.gg HTTP error status %d: %s", response.status, text
                )
                raise StartGGHTTPError(
                    f"Start.gg HTTP {response.status}: {text}",
                    status_code=response.status,
                    response_body=text,
                )

            try:
                result = await response.json()
            except Exception as exc:
                import json

                try:
                    result = json.loads(text)
                except Exception:
                    raise StartGGError(
                        f"Failed to parse JSON response from Start.gg: {text}"
                    ) from exc

            if "errors" in result and result["errors"]:
                errors = result["errors"]
                logger.error("Start.gg GraphQL errors: %s", errors)
                raise StartGGGraphQLError(
                    f"Start.gg GraphQL error: {errors}", errors=errors
                )

            data = result.get("data")
            return data if data is not None else {}

    async def get_event(self, slug: str) -> dict[str, Any] | None:
        """
        Query event information by tournament/event slug.

        Args:
            slug: Event slug (e.g., "tournament/my-tourney/event/singles").

        Returns:
            Event dictionary if found, or None.
        """
        gql = """
        query EventQuery($slug: String!) {
          event(slug: $slug) {
            id
            name
            slug
            state
            numEntrants
            phases {
              id
              name
              phaseGroups {
                nodes {
                  id
                }
              }
            }
          }
        }
        """
        data = await self.query(gql, {"slug": slug})
        return data.get("event")

    async def get_sets(
        self, event_id: int, page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        """
        Query sets for a specific event with pagination.

        Args:
            event_id: The ID of the event.
            page: Page number (1-indexed).
            per_page: Number of sets per page.

        Returns:
            Dictionary containing pageInfo and nodes for event sets.
        """
        gql = """
        query EventSets($eventId: ID!, $page: Int!, $perPage: Int!) {
          event(id: $eventId) {
            sets(page: $page, perPage: $perPage, sortType: STANDARD) {
              pageInfo { total totalPages page perPage }
              nodes {
                id
                state
                round
                fullRoundText
                slots {
                  entrant {
                    id
                    name
                    participants {
                      gamerTag
                      user { id slug }
                    }
                  }
                  standing { stats { score { value } } }
                }
                winnerId
              }
            }
          }
        }
        """
        data = await self.query(
            gql,
            {
                "eventId": event_id,
                "page": page,
                "perPage": per_page,
            },
        )
        event_data = data.get("event")
        if not event_data:
            return {}
        return event_data.get("sets", {})

    async def report_set(
        self,
        set_id: int,
        winner_id: int,
        game_data: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Report the outcome of a bracket set.

        Args:
            set_id: ID of the set being reported.
            winner_id: Entrant ID of the winner.
            game_data: Optional list of game results (score/characters).

        Returns:
            Dictionary with the updated set id and state.
        """
        gql = """
        mutation ReportSet($setId: ID!, $winnerId: ID!, $gameData: [BracketSetGameDataInput]) {
          reportBracketSet(setId: $setId, winnerId: $winnerId, gameData: $gameData) {
            id
            state
          }
        }
        """
        variables: dict[str, Any] = {
            "setId": set_id,
            "winnerId": winner_id,
        }
        if game_data is not None:
            variables["gameData"] = game_data

        data = await self.query(gql, variables)
        return data.get("reportBracketSet", {})

    async def update_seeding(
        self, phase_id: int, seed_mapping: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Update seeding order for a phase.

        Args:
            phase_id: ID of the phase to update.
            seed_mapping: List of seed info dicts with seedId/entrantId and seedNum.

        Returns:
            Dictionary containing updated phase ID.
        """
        gql = """
        mutation UpdateSeeding($phaseId: ID!, $seedMapping: [UpdatePhaseSeedInfo]!) {
          updatePhaseSeeding(phaseId: $phaseId, seedMapping: $seedMapping) {
            id
          }
        }
        """
        data = await self.query(
            gql,
            {
                "phaseId": phase_id,
                "seedMapping": seed_mapping,
            },
        )
        return data.get("updatePhaseSeeding", {})

    async def get_entrants(
        self, event_id: int, page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        """
        Query entrants for an event with pagination.

        Args:
            event_id: The ID of the event.
            page: Page number (1-indexed).
            per_page: Number of entrants per page.

        Returns:
            Dictionary containing pageInfo and nodes for event entrants.
        """
        gql = """
        query EventEntrants($eventId: ID!, $page: Int!, $perPage: Int!) {
          event(id: $eventId) {
            entrants(query: { page: $page, perPage: $perPage }) {
              pageInfo {
                total
                totalPages
                page
                perPage
              }
              nodes {
                id
                name
                isDisqualified
                skill
                participants {
                  id
                  gamerTag
                  prefix
                  user {
                    id
                    slug
                    name
                    discriminator
                  }
                }
              }
            }
          }
        }
        """
        data = await self.query(
            gql,
            {
                "eventId": event_id,
                "page": page,
                "perPage": per_page,
            },
        )
        event_data = data.get("event")
        if not event_data:
            return {}
        return event_data.get("entrants", {})

    async def resolve_user(self, slug: str) -> dict[str, Any] | None:
        """
        Look up a Start.gg user profile by user slug.

        Args:
            slug: User slug (e.g., "user/12345abc" or "12345abc").

        Returns:
            User dictionary if found, or None.
        """
        # Ensure user slug format
        user_slug = slug if slug.startswith("user/") else f"user/{slug}"
        gql = """
        query UserQuery($slug: String!) {
          user(slug: $slug) {
            id
            slug
            name
            discriminator
            bio
            player {
              id
              gamerTag
              prefix
            }
            authorizations {
              type
              externalUsername
            }
          }
        }
        """
        data = await self.query(gql, {"slug": user_slug})
        return data.get("user")

    async def close(self) -> None:
        """Close the underlying aiohttp ClientSession."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> StartGGClient:
        """Enter async context manager."""
        await self._ensure_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context manager and close session."""
        await self.close()
