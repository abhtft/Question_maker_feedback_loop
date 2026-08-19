from litellm_fallback import LiteLLMFallbackClient

# 1. Initialize the client
client = LiteLLMFallbackClient()

# 2. Call generate_content (automatically falls back through Bedrock -> Azure -> OpenRouter)
try:
    response = client.generate_content("")
    print("Response:\n", response)
except Exception as e:
    print("Error querying LLM providers:", e)