import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_ecr as ecr
import aws_cdk.aws_iam as iam
import aws_cdk.aws_rds as rds
from aws_cdk import RemovalPolicy, Stack
from constructs import Construct


class BackendStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = self.create_vpc()

        self.create_ec2_instance(vpc)

        self.create_rds_instance(vpc)

        self.create_ecr_repo()

    def create_ec2_instance(self, vpc: ec2.Vpc):
        ec2.Instance(
            self,
            "ec2-slotify-api",
            vpc=vpc,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T4G, ec2.InstanceSize.SMALL
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

    def create_rds_instance(self, vpc: ec2.Vpc):
        rds.DatabaseInstance(
            self,
            "rds-slotify-database",
            engine=rds.DatabaseInstanceEngine.maria_db(
                version=rds.MariaDbEngineVersion.VER_10_11,
            ),
            # optional, defaults to m5.large
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.SMALL
            ),
            credentials=rds.Credentials.from_generated_secret("syscdk"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
        )

    def create_vpc(self) -> ec2.Vpc:
        return ec2.Vpc(
            self,
            "vpc-ew2-p-slotify",
            # We only need ip addresses for:
            # - API
            # - Database
            # - Router
            # - Broadcast address
            # - Network Address
            ip_addresses=ec2.IpAddresses.cidr("10.0.1.0/29"),
        )

    def create_ecr_repo(self):
        ecr_repository = ecr.Repository(
            self,
            "SlotifyRepository",
            repository_name="ecr-slotify-api",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Optional: Add permissions to allow access to the repository (e.g., EC2 or Lambda)
        ecr_repository.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["ecr:*"],
                resources=[ecr_repository.repository_arn],
                effect=iam.Effect.ALLOW,
                # principals=[iam.ArnPrincipal("*")],
            )
        )
