from livekit.agents import AgentSession, llm


class ConversationActions:
    """Actions to control conversation flow and responses"""
    
    def __init__(self, session: AgentSession):
        """Initialize with agent session
        
        Args:
            session: The AgentSession to interact with
        """
        self.session = session

    async def repeat(self, text: str):
        """Directly speaks the provided text
        
        Args:
            text: The text to speak to the user
        """
        await self.session.say(text)

    async def respond(
        self, 
        chat_ctx: llm.ChatContext, 
        instructions: str = None
    ):
        """Generate a reply using specific context and instructions
        
        This gives you full control over the conversation history
        
        Args:
            chat_ctx: The chat context to use for generation
            instructions: Optional custom instructions for this response
        """
        await self.session.generate_reply(
            instructions=instructions,
            chat_ctx=chat_ctx
        )