#!/usr/bin/env python

import boto3
import chainlit as cl
import json
import logging

# Initialize Bedrock
BEDROCK_MODEL_ID = "us.amazon.nova-micro-v1:0"

def get_bedrock_runtime_client(region="us-west-2"):
    return boto3.client(
        service_name='bedrock-runtime',
        region_name=region
    )
bedrock_runtime = get_bedrock_runtime_client()

@cl.on_chat_start
async def on_chat_start():
    welcome_message = "Welcome to the Chainlit + Amazon Bedrock chat app! How can I help you today?"
    cl.user_session.set(
        "message_history",
        [{"role": "system", "content": welcome_message}],
    )

@cl.on_message
async def on_message(message: cl.Message):
    message_history = cl.user_session.get("message_history")
    message_history.append({"role": "user", "content": message.content})

    # Create a message object to be displayed in the UI
    msg = cl.Message(content="")

    # Prepare the messages for Bedrock
    messages = [{"role": "user", "content": [{"text": message.content}]}]
    response = bedrock_runtime.converse_stream(
        modelId = BEDROCK_MODEL_ID,
        messages = messages,
        inferenceConfig = {"temperature": 0.1}
    )
    stream = response.get('stream')
    logging.info(f"STREAM: {json.dumps(stream, indent=4, default=str)}")

    # Process the streaming response
    response_text = ""
    for event in stream:
        # logging.info(f"JSON: {json.dumps(event)}")
        if 'contentBlockDelta' in event:
            contentBlockDelta = event['contentBlockDelta']
            if 'delta' in contentBlockDelta:
                delta = contentBlockDelta['delta']
                if 'text' in delta:
                    text_chunk = delta['text']
                    response_text += text_chunk
                    # Fix: Use content_update instead of update with content kwarg
                    await msg.stream_token(text_chunk)
        elif 'messageStart' in event:
            messageStart = event['messageStart']
            role = messageStart.get('role')
            # { "messageStart": { "role": "assistant" } } }
        elif 'contentBlockStop' in event:
            # { "contentBlockStop": { "contentBlockIndex": 0 } }
            pass
        elif 'metadata' in event:
            metadata = event['metadata']
            # {
            #     "metadata": {
            #         "usage": {
            #             "inputTokens": 1,
            #             "outputTokens": 38,
            #             "totalTokens": 39
            #         },
            #         "metrics": {
            #             "latencyMs": 365
            #         }
            #     }
            # }
            metadata_txt = ''
            if 'usage' in metadata:
                usage = metadata['usage']
                inputTokens = usage.get('inputTokens')
                outputTokens = usage.get('outputTokens')
                totalTokens = usage.get('totalTokens')
                metadata_txt += f"\n**Tokens**: {inputTokens} (input), {outputTokens} (output), {totalTokens} (total)"
            if 'metrics' in metadata:
                metrics = metadata['metrics']
                metadata_txt += f" \n**Latency**: {metrics['latencyMs']} (ms)"
            await msg.stream_token(metadata_txt)
    
    if not response_text:
        await msg.update("I apologize, but I was unable to generate a response. Please try again.")


if __name__ == "__main__":
    cl.run()
