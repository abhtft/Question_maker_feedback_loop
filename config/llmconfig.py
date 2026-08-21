"""

Test the connection to AWS Bedrock, Azure OpenAI, and OpenRouter using LiteLLM.


python config/llmconfig.py

# 1. First test the model:
# curl -X POST "https://openrouter.ai/api/v1/chat/completions" \
#   -H "Authorization: Bearer TOKEN" \
#   -H "Content-Type: application/json" \
#   -d "{\"model\": \"google/gemini-2.5-pro\", \"messages\": [{\"role\": \"user\", \"content\": \"Hello, how are you?\"}]}"

# 2. If it works, you can use it in your application
"""


import os
import sys
import logging

logger = logging.getLogger("LiteLLMConnectionManager")

# Helper to check and prompt for installing requirements
def check_dependencies():
    missing = []
    try:
        import dotenv
    except ImportError:
        missing.append("python-dotenv")
    try:
        import litellm
    except ImportError:
        missing.append("litellm")
    
    if missing:
        print("=" * 80)
        print("WARNING: Missing required Python dependencies!")
        print(f"Please install them using: pip install {' '.join(missing)}")
        print("=" * 80)
        return False
    return True

# Try loading python-dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class LiteLLMFallbackClient:
    """
    A unified LLM Client that implements fallback logic in the following priority:
    1. AWS Bedrock (bedrock/*)
    2. Azure OpenAI (azure/*)
    3. OpenRouter (openrouter/*)
    
    Using LiteLLM to standardise the completion requests.
    """

    def __init__(self):
        self.candidates = []
        self._detect_configurations()

    def _is_valid_value(self, value):
        if not value:
            return False
        # Ignore empty values and sample configuration placeholders
        placeholders = ["your_", "_here", "placeholder"]
        return not any(p in value.lower() for p in placeholders)

    def _detect_configurations(self):
        # 1. AWS Bedrock detection
        aws_key = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret = os.getenv("AWS_SECRET_ACCESS_KEY")
        aws_region = os.getenv("AWS_REGION_NAME") or os.getenv("AWS_REGION")
        aws_model = os.getenv("AWS_BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")

        # LiteLLM looks for AWS variables standard in environment.
        # If they are valid, we register Bedrock as priority 1 candidate.
        if self._is_valid_value(aws_key) and self._is_valid_value(aws_secret) and self._is_valid_value(aws_region):
            self.candidates.append({
                "provider": "AWS Bedrock",
                "model_identifier": f"bedrock/{aws_model}",
                "env_check": True
            })
        else:
            self.candidates.append({
                "provider": "AWS Bedrock",
                "model_identifier": f"bedrock/{aws_model}",
                "env_check": False
            })

        # 2. Azure OpenAI detection
        azure_key = os.getenv("AZURE_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
        azure_base = os.getenv("AZURE_API_BASE") or os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_version = os.getenv("AZURE_API_VERSION") or os.getenv("AZURE_OPENAI_API_VERSION") or "2024-06-01"
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

        if self._is_valid_value(azure_key) and self._is_valid_value(azure_base) and self._is_valid_value(azure_deployment):
            # Map values to LiteLLM standard environment variables if not already mapped
            os.environ["AZURE_API_KEY"] = azure_key
            os.environ["AZURE_API_BASE"] = azure_base
            os.environ["AZURE_API_VERSION"] = azure_version
            
            self.candidates.append({
                "provider": "Azure OpenAI",
                "model_identifier": f"azure/{azure_deployment}",
                "env_check": True
            })
        else:
            azure_model_placeholder = azure_deployment or "gpt-4o"
            self.candidates.append({
                "provider": "Azure OpenAI",
                "model_identifier": f"azure/{azure_model_placeholder}",
                "env_check": False
            })

        # 3. OpenRouter detection
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        openrouter_model = os.getenv("OPENROUTER_MODEL_ID", "google/gemini-2.5-pro")

        if self._is_valid_value(openrouter_key):
            # Set OPENROUTER_API_KEY standard in environment
            os.environ["OPENROUTER_API_KEY"] = openrouter_key
            self.candidates.append({
                "provider": "OpenRouter",
                "model_identifier": f"openrouter/{openrouter_model}",
                "env_check": True
            })
        else:
            self.candidates.append({
                "provider": "OpenRouter",
                "model_identifier": f"openrouter/{openrouter_model}",
                "env_check": False
            })

    def generate_content(self, prompt: str) -> str:
        """
        Attempts to call the configured providers in order of priority:
        AWS Bedrock -> Azure OpenAI -> OpenRouter using LiteLLM completions.
        """
        configured_candidates = [c for c in self.candidates if c["env_check"]]

        if not configured_candidates:
            raise RuntimeError(
                "No LLM providers are configured in the environment. Please populate your .env file."
            )

        import litellm
        # Opt out of LiteLLM usage telemetry
        litellm.telemetry = False
        
        errors = {}

        for candidate in configured_candidates:
            provider = candidate["provider"]
            model = candidate["model_identifier"]
            
            logger.info(f"Attempting {provider} using LiteLLM ({model})...")
            try:
                # Call LiteLLM standardized completions API
                response = litellm.completion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    # Let LiteLLM propagate standard API/network timeouts (default 600s, customisable)
                    timeout=30
                )
                logger.info(f"SUCCESS: {provider} responded successfully.")
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"{provider} failed: {e}")
                errors[provider] = str(e)

        # If all configured providers failed
        error_summary = "\n".join([f" - {provider}: {err}" for provider, err in errors.items()])
        raise RuntimeError(
            f"All configured LLM providers failed:\n{error_summary}"
        )
# Try to import LangChain elements for a compatible wrapper
try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import BaseMessage, AIMessage
    from langchain_core.outputs import ChatResult, ChatGeneration
    from typing import Any, List, Optional
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

if HAS_LANGCHAIN:
    class LiteLLMChatWrapper(BaseChatModel):
        """
        A LangChain-compatible wrapper for LiteLLMFallbackClient.
        """
        client: Any = None

        def __init__(self, client: Any = None, **kwargs):
            if client is None:
                client = LiteLLMFallbackClient()
            super().__init__(client=client, **kwargs)

        def _generate(
            self,
            messages: List[BaseMessage],
            stop: Optional[List[str]] = None,
            run_manager: Optional[Any] = None,
            **kwargs: Any,
        ) -> ChatResult:
            prompt_str = "\n".join([m.content if hasattr(m, 'content') else str(m) for m in messages])
            response_text = self.client.generate_content(prompt_str)
            message = AIMessage(content=response_text)
            generation = ChatGeneration(message=message)
            return ChatResult(generations=[generation])

        @property
        def _llm_type(self) -> str:
            return "litellm_fallback_wrapper"


def main():
    # Configure basic logging to console for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    if not check_dependencies():
        sys.exit(1)
        
    print("\n" + "="*80)
    print("  LiteLLM Multi-Provider Fallback Connection Client")
    print("="*80)
    
    client = LiteLLMFallbackClient()
    
    print("\n--- Provider Configurations Detect status ---")
    for candidate in client.candidates:
        status = "CONFIGURED" if candidate["env_check"] else "NOT CONFIGURED / MISSING KEYS"
        print(f"{candidate['provider']:<18}: {status:<15} (Model: {candidate['model_identifier']})")
    print("-" * 80)
    
    # Prompt the user for input or use command line arg
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = input("\nEnter a prompt to test connection: ").strip()
        if not prompt:
            prompt = "Say 'Hello World' and identify which LLM provider and model you are."
            print(f"Using default prompt: '{prompt}'")
            
    print(f"\nProcessing prompt: '{prompt}'...")
    try:
        response = client.generate_content(prompt)
        print("\n" + "="*80)
        print("  SUCCESSFUL RESPONSE (via LiteLLM)")
        print("="*80)
        print(response)
        print("="*80 + "\n")
    except Exception as e:
        print("\n" + "!"*80)
        print("  CONNECTION ERROR")
        print("!"*80)
        print(e)
        print("!"*80 + "\n")


if __name__ == "__main__":
    main()
