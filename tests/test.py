import google.generativeai as genai

# Authenticate (API key must be set in your environment or passed here)
genai.configure(api_key="AIzaSyDwpxZ9xw511Btlrdcr2rInc8Ck2WOgh0A")

# List available models
models = genai.list_models()
for model in models:
    print(model.name, "-", model.supported_generation_methods)