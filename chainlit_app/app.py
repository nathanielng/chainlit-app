import os
import boto3
import chainlit as cl
from chainlit.types import AskFileResponse

# Initialize Bedrock client
def get_bedrock_runtime_client(region="us-west-2"):
    return boto3.client(
        service_name='bedrock-runtime',
        region_name=region
    )

bedrock_runtime = get_bedrock_runtime_client()
MODEL_ID = "us.amazon.nova-micro-v1:0"

@cl.on_chat_start
async def on_chat_start():
    # Set the initial message
    await cl.Message(
        content="Welcome to the Chainlit + Amazon Bedrock chat app! How can I help you today?",
        author="System"
    ).send()

@cl.on_message
async def on_message(message: cl.Message):
    # Create a message object to be displayed in the UI
    msg = cl.Message(content="")
    
    # Start streaming the response
    async with msg.content_stream() as stream:
        # Prepare the messages for Bedrock
        messages = [{"role": "user", "content": [{"text": message.content}]}]
        
        # Call Bedrock with streaming
        response_stream = bedrock_runtime.converse_stream(
            modelId=MODEL_ID,
            messages=messages,
            inferenceConfig={"temperature": 0.1}
        )
        
        # Process the streaming response
        for event in response_stream:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'message' in chunk:
                    message_content = chunk['message'].get('content', [])
                    for content_item in message_content:
                        if content_item.get('type') == 'text':
                            text_chunk = content_item.get('text', '')
                            await stream.write(text_chunk)

if __name__ == "__main__":
    cl.run()
