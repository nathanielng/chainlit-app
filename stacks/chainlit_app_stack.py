from aws_cdk import (
    Duration,
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets,
    aws_ecs_patterns as ecs_patterns,
    aws_iam as iam,
    aws_logs as logs,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_certificatemanager as acm,
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
                }
            ),
            public_load_balancer=True
        )

        # Create CloudFront distribution
        distribution = cloudfront.Distribution(
            self, "ChainlitDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.LoadBalancerV2Origin(
                    fargate_service.load_balancer,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                    connection_attempts=3,
                    connection_timeout=Duration.seconds(10)
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED
            )
        )

        # Add permissions for Bedrock
        bedrock_policy = iam.PolicyStatement(
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:Converse",
                "bedrock:ConverseStream"
            ],
            resources=["*"]  # You might want to restrict this to specific model ARNs in production
        )

        fargate_service.task_definition.task_role.add_to_policy(bedrock_policy)

        # Output the URLs
        # CfnOutput(
        #     self, "ChainlitAppURL",
        #     value=fargate_service.load_balancer.load_balancer_dns_name,
        #     description="URL of the ALB"
        # )

        CfnOutput(
            self, "ChainlitCloudFrontURL",
            value=distribution.distribution_domain_name,
            description="CloudFront URL of the Chainlit application"
        )
