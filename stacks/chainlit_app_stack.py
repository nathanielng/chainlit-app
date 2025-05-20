from aws_cdk import (
    Duration,
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets,
    aws_ecs_patterns as ecs_patterns,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_certificatemanager as acm,
    aws_elasticloadbalancingv2 as elbv2,
    aws_secretsmanager as secretsmanager,
    CfnOutput
)
from constructs import Construct

class ChainlitAppStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a VPC
        vpc = ec2.Vpc(
            self, "ChainlitVPC",
            max_azs=2,
            nat_gateways=1
        )

        # Create an ECS cluster
        cluster = ecs.Cluster(
            self, "ChainlitCluster",
            vpc=vpc
        )

        # Create secret for custom header value
        custom_header_secret = secretsmanager.Secret(
            self, "CustomHeaderSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                exclude_characters='/@"',
                password_length=32
            )
        )

        # Build Docker image from local directory
        asset = ecr_assets.DockerImageAsset(
            self, "ChainlitDockerImage",
            directory="./chainlit_app"
        )

        # Create a Fargate service
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "ChainlitService",
            cluster=cluster,
            memory_limit_mib=2048,
            cpu=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_docker_image_asset(asset),
                container_port=8000,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="chainlit",
                    log_retention=logs.RetentionDays.ONE_YEAR
                ),
                environment={
                    "LOG_LEVEL": "INFO"
                },
                secrets={
                    "CUSTOM_HEADER_VALUE": ecs.Secret.from_secrets_manager(custom_header_secret)
                }
            ),
            public_load_balancer=True
        )

        # Add ALB listener rule to check for custom header
        allow_rule = elbv2.CfnListenerRule(
            self, "AllowWithHeader",
            listener_arn=fargate_service.listener.listener_arn,
            priority=10,
            conditions=[{
                "field": "http-header",
                "httpHeaderConfig": {
                    "httpHeaderName": "X-Custom-Header",
                    "values": [custom_header_secret.secret_value.unsafe_unwrap()]
                }
            }],
            actions=[{
                "type": "forward",
                "targetGroupArn": fargate_service.target_group.target_group_arn
            }]
        )

        # Add default deny rule with lower priority
        deny_rule = elbv2.CfnListenerRule(
            self, "DefaultDeny",
            listener_arn=fargate_service.listener.listener_arn,
            priority=20,
            conditions=[{
                "field": "path-pattern",
                "values": ["*"]
            }],
            actions=[{
                "type": "fixed-response",
                "fixedResponseConfig": {
                    "statusCode": "403",
                    "contentType": "text/plain",
                    "messageBody": "Access denied"
                }
            }]
        )

        # Create S3 bucket for CloudFront logs
        logs_bucket = s3.Bucket(
            self,
            "CloudFrontLogsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            object_ownership=s3.ObjectOwnership.OBJECT_WRITER,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days(90)  # Retain logs for 90 days
                )
            ]
        )

        # Create CloudFront distribution with logging enabled
        distribution = cloudfront.Distribution(
            self,
            "ChainlitDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.LoadBalancerV2Origin(
                    fargate_service.load_balancer,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                    connection_attempts=3,
                    connection_timeout=Duration.seconds(10),
                    custom_headers={
                        "X-Custom-Header": custom_header_secret.secret_value.unsafe_unwrap()
                    }
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                # Forwards all viewer request headers, query strings, and cookies to the origin
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER
            ),
            # Enable access logging
            log_bucket=logs_bucket,
            log_file_prefix="cloudfront-logs/"
        )

        # Add permissions for Bedrock
        bedrock_policy = iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:Converse",
                "bedrock:ConverseStream"
            ],
            resources=["arn:aws:bedrock:*:*:model/*"]  # Restrict to Bedrock model ARNs
        )

        fargate_service.task_definition.task_role.add_to_policy(bedrock_policy)

        # Output the URLs
        CfnOutput(
            self, "ChainlitCloudFrontURL",
            value=distribution.distribution_domain_name,
            description="CloudFront URL of the Chainlit application"
        )

        CfnOutput(
            self, "CustomHeaderSecretARN",
            value=custom_header_secret.secret_arn,
            description="ARN of the custom header secret in Secrets Manager"
        )
