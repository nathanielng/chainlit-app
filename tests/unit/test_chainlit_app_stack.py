import aws_cdk as core
import aws_cdk.assertions as assertions

from chainlit_app.chainlit_app_stack import ChainlitAppStack

# example tests. To run these tests, uncomment this file along with the example
# resource in chainlit_app/chainlit_app_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = ChainlitAppStack(app, "chainlit-app")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
