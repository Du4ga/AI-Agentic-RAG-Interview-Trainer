"""
Granite Client — IBM watsonx.ai text generation via REST API
"""
import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

IAM_TOKEN_URL = "https://iam.eu-de.bluemix.net/identity/token"
FALLBACK_IAM_URL = "https://iam.cloud.ibm.com/identity/token"


class GraniteClient:
    def __init__(self):
        self.api_key = os.getenv("WATSONX_API_KEY", "")
        self.project_id = os.getenv("WATSONX_PROJECT_ID", "dc4b7029-c061-4cff-8bdf-464892b7c2ef")
        self.model_id = os.getenv("WATSONX_MODEL_ID", "ibm/granite-4-h-small")
        self.base_url = os.getenv(
            "WATSONX_URL",
            "https://eu-de.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
        )
        self._iam_token: str = ""

    async def _get_iam_token(self) -> str:
        """Fetch a fresh IAM token from IBM Cloud."""
        data = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": self.api_key
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        for url in [IAM_TOKEN_URL, FALLBACK_IAM_URL]:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(url, data=data, headers=headers)
                    if resp.status_code == 200:
                        self._iam_token = resp.json()["access_token"]
                        return self._iam_token
            except Exception as e:
                logger.warning(f"IAM token attempt failed ({url}): {e}")
        raise RuntimeError("Failed to obtain IAM token from IBM Cloud")

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 800,
        temperature: float = 0.7,
        stop_sequences: list = None
    ) -> str:
        """Generate text using IBM Granite on watsonx.ai."""
        token = await self._get_iam_token()

        payload = {
            "model_id": self.model_id,
            "project_id": self.project_id,
            "input": prompt,
            "parameters": {
                "decoding_method": "greedy" if temperature == 0 else "sample",
                "max_new_tokens": max_tokens,
                "temperature": temperature,
                "repetition_penalty": 1.1,
                "stop_sequences": stop_sequences or []
            }
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(self.base_url, json=payload, headers=headers)
                resp.raise_for_status()
                result = resp.json()
                generated = result.get("results", [{}])[0].get("generated_text", "").strip()
                logger.info(f"Granite generated {len(generated)} chars")
                return generated
        except httpx.HTTPStatusError as e:
            logger.error(f"Granite HTTP error {e.response.status_code}: {e.response.text}")
            raise RuntimeError(f"Granite API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Granite call failed: {e}")
            raise RuntimeError(f"Granite call failed: {e}")
