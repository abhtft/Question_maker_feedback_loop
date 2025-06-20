import os
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

endpoint = "https://learningabhishekquestionmakerapp.openai.azure.com/"
model_name = "gpt-4.1"
deployment = "gpt-4.1"

subscription_key = os.getenv('AZURE_OPENAI_API_KEY')
api_version = "2025-01-01-preview"  # Assuming this is a valid or future-supported version

client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=subscription_key,
)

response = client.chat.completions.create(
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant. Please provide your response in JSON format.",
        },
        {
            "role": "user",
            "content": "I am going to Paris, what should I see?",
        }
    ],
    max_tokens=800,
    temperature=1.0,
    top_p=1.0,
    frequency_penalty=0.0,
    presence_penalty=0.0,
    model=deployment,
    response_format={"type": "json_object"}  # Correct object format
)

print(response.choices[0].message.content)
