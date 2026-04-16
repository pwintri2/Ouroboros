class ChatGPTAdapter:
    def __init__(self, api_key=None):
        self.api_key = api_key

    def send_message(self, message):
        # Mocking the response as I don't have a live ChatGPT API key
        return f"ChatGPT (Mock): The weather tomorrow will be sunny with a high of 22°C."
