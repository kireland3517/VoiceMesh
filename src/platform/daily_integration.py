"""Daily.co integration for SignalWire → Pipecat bridge."""

import time
import aiohttp
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger()


class DailyRoomManager:
    """
    Manage Daily.co rooms for SignalWire call bridging.

    Architecture:
    1. SignalWire call comes in
    2. Create Daily room with SIP enabled
    3. Start Pipecat pipeline connected to Daily room (WebRTC)
    4. SignalWire dials into Daily room via SIP
    5. Audio flows: SignalWire (SIP) ↔ Daily (WebRTC) ↔ Pipecat ↔ Deepgram/Cartesia
    """

    def __init__(self, api_key: str):
        """
        Initialize Daily room manager.

        Args:
            api_key: Daily.co API key from dashboard.daily.co/developers
        """
        self.api_key = api_key
        self.base_url = "https://api.daily.co/v1"

        # Debug logging to verify API key is loaded (log first 8 chars for security)
        logger.info(
            "daily_manager_initialized",
            api_key_preview=api_key[:8] + "..." if api_key and len(api_key) > 8 else "EMPTY",
            api_key_length=len(api_key) if api_key else 0
        )

    async def create_room(
        self,
        call_id: str,
        enable_recording: bool = True
    ) -> Dict[str, Any]:
        """
        Create a Daily.co room for a voice call.

        Args:
            call_id: Unique identifier for this call
            enable_recording: Whether to record the call

        Returns:
            Dictionary with room URL, token, and SIP endpoint
            {
                "room_name": str,
                "url": str,
                "token": str,
                "sip_endpoint": str,  # Format: <call_id>@sip.daily.co
                "expires": int  # Unix timestamp
            }
        """
        room_name = f"voicemesh-{call_id}"

        logger.info(
            "creating_daily_room",
            call_id=call_id,
            room_name=room_name
        )

        async with aiohttp.ClientSession() as session:
            # Create room with SIP enabled
            async with session.post(
                f"{self.base_url}/rooms",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "name": room_name,
                    "privacy": "private",
                    "properties": {
                        "exp": int(time.time() + 3600),  # Expire 1 hour from now (Unix timestamp)
                        "enable_chat": False,
                        "enable_screenshare": False,
                        "enable_knocking": False,
                        "enable_prejoin_ui": False,
                        "start_audio_off": False,
                        "start_video_off": True,  # Audio only
                        "enable_recording": "cloud" if enable_recording else None,
                        "sip": {
                            "display_name": "VoiceMesh AI",
                            "video": False,
                            "sip_mode": "dial-in"
                        }
                    }
                }
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(
                        "daily_room_creation_failed",
                        status=resp.status,
                        error=error_text
                    )
                    raise Exception(f"Failed to create Daily room: {error_text}")

                room_data = await resp.json()

            # Debug logging to see actual response structure
            logger.info(
                "daily_room_response_received",
                room_data_keys=list(room_data.keys()),
                config_keys=list(room_data.get("config", {}).keys()) if "config" in room_data else None
            )

            # Create meeting token for bot
            token = await self._create_meeting_token(session, room_name)

            # Get the SIP URI directly from Daily.co's API response
            sip_uri = room_data["config"]["sip_uri"]

            logger.info(
                "daily_room_created",
                room_name=room_name,
                url=room_data["url"],
                sip_uri=sip_uri
            )

            return {
                "room_name": room_name,
                "url": room_data["url"],
                "token": token,
                "sip_uri": sip_uri,
                "expires": room_data["config"]["exp"]
            }

    async def _create_meeting_token(
        self,
        session: aiohttp.ClientSession,
        room_name: str
    ) -> str:
        """
        Create a meeting token for the bot to join the room.

        Args:
            session: Aiohttp session
            room_name: Name of the room

        Returns:
            Meeting token string
        """
        async with session.post(
            f"{self.base_url}/meeting-tokens",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "properties": {
                    "room_name": room_name,
                    "is_owner": True,
                    "user_name": "VoiceMesh Bot"
                }
            }
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(
                    "daily_token_creation_failed",
                    status=resp.status,
                    error=error_text
                )
                raise Exception(f"Failed to create meeting token: {error_text}")

            data = await resp.json()
            return data["token"]

    async def delete_room(self, room_name: str) -> None:
        """
        Delete a Daily.co room after call ends.

        Args:
            room_name: Name of the room to delete
        """
        logger.info("deleting_daily_room", room_name=room_name)

        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self.base_url}/rooms/{room_name}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as resp:
                if resp.status not in [200, 404]:  # 404 is ok, room might be auto-deleted
                    error_text = await resp.text()
                    logger.warning(
                        "daily_room_deletion_failed",
                        status=resp.status,
                        error=error_text
                    )
                else:
                    logger.info("daily_room_deleted", room_name=room_name)

    async def get_room_info(self, room_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a Daily room.

        Args:
            room_name: Name of the room

        Returns:
            Room information or None if not found
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/rooms/{room_name}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as resp:
                if resp.status == 404:
                    return None
                elif resp.status != 200:
                    error_text = await resp.text()
                    logger.error(
                        "daily_room_info_failed",
                        status=resp.status,
                        error=error_text
                    )
                    return None

                return await resp.json()
