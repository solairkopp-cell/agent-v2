# ==================== SESSION MANAGER ====================

class SessionManager:
    """
    Centralizes session closure and room deletion to ensure zero quota leak.
    """

    def __init__(self, room_context, agent_session, speech_service, session_logger):
        # Using explicit names as requested
        self.room_context = room_context
        self.agent_session = agent_session
        self.speech_service = speech_service
        self.session_logger = session_logger
        self.is_closed = False

    async def terminate(self, reason: str = "normal_end"):
        """
        Orchestrates the shutdown sequence of all active services.
        """
        if self.is_closed:
            return
        
        self.is_closed = True
        self.session_logger.add_event(f"SESSION TERMINATION STARTED: {reason}")

        # 1. Stop ongoing TTS tasks
        await self._stop_speech_service()

        # 2. Close agent session
        await self._close_agent_session()

        # 3. Disconnect and Delete Room
        await self._cleanup_room_resources()

    async def _stop_speech_service(self):
        """
        Cancels any pending or active speech generation tasks.
        """
        if self.speech_service.current_task and not self.speech_service.current_task.done():
            self.speech_service.current_task.cancel()
            self.session_logger.add_event("Speech task cancelled")

    async def _close_agent_session(self):
        """
        Gracefully closes the agent communication channel.
        """
        try:
            await self.agent_session.aclose()
            self.session_logger.add_event("Agent session closed")
        except Exception as error:
            self.session_logger.add_event(f"Error closing agent session: {error}")

    async def _cleanup_room_resources(self):
        """
        Disconnects from the room and triggers physical deletion to release quota.
        """
        # Disconnect first
        try:
            await self.room_context.room.disconnect()
            self.session_logger.add_event("Room disconnected")
        except Exception as error:
            self.session_logger.add_event(f"Room disconnect error: {error}")

        # Final deletion (The most important for quota)
        try:
            room_name = self.room_context.room.name
            await self.room_context.api.room.delete_room(room_name)
            self.session_logger.add_event(f"Room '{room_name}' deleted (quota released)")
        except Exception as error:
            self.session_logger.add_event(f"Critical: Room deletion failed: {error}")