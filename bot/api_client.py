import aiohttp
import asyncio
from typing import Optional, Dict, Any
from aiohttp.client_exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

class LLMAPIClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(self.username, self.password)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
    
    async def create_session(self) -> Optional[str]:
        """Create a new session and return session_id"""
        try:
            url = f"{self.base_url}/create-session"
            async with self._session.post(url) as response:
                if response.status == 200:
                    data = await response.json()
                    session_id = data.get("session_id")
                    if session_id:
                        logger.info(f"Session created: {session_id}")
                        return session_id
                    else:
                        logger.error("Session ID not received")
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to create session: {response.status} - {error_text}")
                    return None
        except ClientError as e:
            logger.error(f"Error creating session: {e}")
            return None
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a specific session"""
        try:
            url = f"{self.base_url}/delete-session"
            payload = {"session_id": session_id}
            headers = {"Content-Type": "application/json"}
            
            async with self._session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    logger.info(f"Session deleted: {session_id}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to delete session: {response.status} - {error_text}")
                    return False
        except ClientError as e:
            logger.error(f"Error deleting session: {e}")
            return False
    
    async def query(self, question: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Send a query to the LLM API with optional session_id"""
        try:
            url = f"{self.base_url}/query"
            payload = {
                "query": question
            }
            
            # Add session_id if provided
            if session_id:
                payload["session_id"] = session_id
            
            headers = {"Content-Type": "application/json"}
            
            async with self._session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"Query failed: {response.status} - {error_text}")
                    return None
        except ClientError as e:
            logger.error(f"Error during query: {e}")
            return None

    async def query_with_session_management(self, question: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Send a query with automatic session creation if session_id is not provided.
        This method is useful when you want the client to automatically manage sessions.
        """
        # If no session_id provided, create a new one
        if not session_id:
            session_id = await self.create_session()
            if not session_id:
                logger.error("Failed to create session for query")
                return None
        
        # Send the query with the session_id
        result = await self.query(question, session_id)
        
        # If query failed due to invalid session, try creating a new one
        if result is None:
            logger.info("Query failed, attempting to create new session...")
            new_session_id = await self.create_session()
            if new_session_id:
                result = await self.query(question, new_session_id)
        
        return result