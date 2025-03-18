import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_ecr as ecr
import aws_cdk.aws_iam as iam
import aws_cdk.aws_logs as logs
import aws_cdk.aws_rds as rds
import aws_cdk.aws_sagemaker as sagemaker
import aws_cdk.aws_s3 as s3
from aws_cdk import RemovalPolicy, Stack
from constructs import Construct


class BackendStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = self.create_vpc()

        ec2_sg = self.create_ec2_security_group(vpc)
        rds_sg = self.create_rds_security_group(vpc, ec2_sg)
        sm_sg = self.create_sm_security_group(vpc)

        key_pair = ec2.KeyPair(
            self,
            "EC2SlotifyKeyPair",
            key_pair_name="slotify-api",
            type=ec2.KeyPairType.RSA,
        )

        self.create_ec2_instance(vpc, ec2_sg, key_pair)

        self.create_rds_instance(vpc, rds_sg)

        self.create_ecr_repo()

        self.create_s3_bucket(vpc)
        
        self.create_sagemaker(vpc, sm_sg)

    def create_ec2_instance(
        self, vpc: ec2.Vpc, sg: ec2.SecurityGroup, key: ec2.IKeyPair
    ):
        role = iam.Role(
            self,
            "EC2ECRRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2ContainerRegistryReadOnly"
                ),  # Permissions to pull from ECR
            ],
        )
        cloud_init_config = ec2.CloudFormationInit.from_config_sets(
            config_sets={"default": ["install"]},
            configs={
                "install": ec2.InitConfig(
                    [
                        ec2.InitCommand.shell_command("sudo yum install -y docker"),
                        ec2.InitCommand.shell_command("sudo service docker start"),
                        ec2.InitCommand.shell_command(
                            "sudo usermod -a -G docker ec2-user"
                        ),
                        ec2.InitCommand.shell_command(
                            "sudo curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose"
                        ),
                        ec2.InitCommand.shell_command(
                            "sudo chmod +x /usr/local/bin/docker-compose"
                        ),
                        ec2.InitCommand.shell_command("sudo yum install -y tmux"),
                        ec2.InitCommand.shell_command("sudo dnf install -y mariadb105"),
                    ]
                ),
            },
        )
        ec2.Instance(
            self,
            "ec2-slotify-api",
            vpc=vpc,
            init=cloud_init_config,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM
            ),
            key_pair=key,
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            role=role,
            security_group=sg,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            user_data=ec2.UserData.custom(
                """
                    #!/bin/bash
                    # Install docker
                    sudo yum update -y
                    sudo yum install -y docker
                    sudo service docker start
                    sudo usermod -a -G docker ec2-user
                    sudo curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose
                    sudo chmod +x /usr/local/bin/docker-compose
                    docker-compose version

                    # install mariadb
                    curl -LsS https://r.mariadb.com/downloads/mariadb_repo_setup | sudo bash

                    #install tmux
                    sudo yum install -y tmux
                """
            ),
        )

    def create_rds_instance(self, vpc: ec2.Vpc, sg: ec2.SecurityGroup):
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
            security_groups=[sg],
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
        )

    def create_vpc(self) -> ec2.Vpc:

        vpc = ec2.Vpc(
            self,
            "vpc-ew2-p-slotify",
            ip_addresses=ec2.IpAddresses.cidr("10.1.0.0/24"),
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public-subnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                ),
                ec2.SubnetConfiguration(
                    name="private-isolated-subnet",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,  # Private isolated subnet
                ),
            ],
        )

        log_group = logs.LogGroup(
            self,
            "VPCSlotifyLogGroup",
            log_group_name="VPCSlotifyFlowLogGroup",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Setup IAM user for logs
        vpc_flow_role = iam.Role(
            self,
            "VPCFlowLogRole",
            assumed_by=iam.ServicePrincipal("vpc-flow-logs.amazonaws.com"),
        )

        log_group.grant_write(vpc_flow_role)

        self.flow_log = ec2.CfnFlowLog(
            self,
            "SlotifyVPCFlowLog",
            resource_id=vpc.vpc_id,
            resource_type="VPC",
            traffic_type="ALL",
            deliver_logs_permission_arn=vpc_flow_role.role_arn,
            log_destination_type="cloud-watch-logs",
            log_group_name=log_group.log_group_name,
            log_format="${traffic-path} ${flow-direction} ${region} ${account-id} ${interface-id} ${srcaddr} ${dstaddr} ${srcport} ${dstport} ${action} ${log-status}",
        )

        return vpc

    def create_ec2_security_group(self, vpc: ec2.Vpc) -> ec2.SecurityGroup:
        sg = ec2.SecurityGroup(
            self,
            "EC2SecurityGroup",
            vpc=vpc,
            description="Allow SSH and outbound to RDS",
            allow_all_outbound=True,  # Allows outgoing traffic
        )

        # Allow SSH access (Optional: restrict to your IP)
        sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(22),
            "Allow SSH access",
        )

        # Allow HTTPS (port 443)
        sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            "Allow HTTPS access",
        )

        return sg

    def create_rds_security_group(
        self, vpc: ec2.Vpc, ec2_sg: ec2.SecurityGroup
    ) -> ec2.SecurityGroup:
        sg = ec2.SecurityGroup(
            self,
            "RDSSecurityGroup",
            vpc=vpc,
            description="Allow access from EC2 instance",
        )

        # Allow incoming connections from EC2 security group on port 3306 (MariaDB)
        sg.add_ingress_rule(
            ec2_sg,  # Allow only EC2 instance to connect
            ec2.Port.tcp(3306),
            "Allow MySQL/MariaDB traffic from EC2 instance",
        )

        return sg

    def create_sm_security_group(
        self, vpc: ec2.Vpc,
    ) -> ec2.SecurityGroup:
        sg = ec2.SecurityGroup(
            self,
            "SMSecurityGroup",
            vpc= vpc,
            allow_all_outbound= True,
            description="Allow access from sagemaker EC2 instances",
        )

        # Allow HTTPS (port 443) for communications iwth SageMaker endpoints
        sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),  # Allow any peer ec2 instances to connect
            ec2.Port.tcp(443),
            "Allow HTTPS traffic",
        )
        
        # Allow Jupyter Notebook (port 8888) access to its instances
        sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),  # Allow any peer ec2 instances to connect
            ec2.Port.tcp(8888),
            "Allow Jupyter Notebook access",
        )
        
        return sg
    
    def create_ecr_repo(self):
        ecr.Repository(
            self,
            "SlotifyRepository",
            lifecycle_rules=[
                ecr.LifecycleRule(
                    description="Keep only the latest image",
                    rule_priority=1,
                    tag_status=ecr.TagStatus.ANY,
                    max_image_count=1,  # Keep only 1 latest image
                )
            ],
            repository_name="ecr-slotify-api",
            removal_policy=RemovalPolicy.DESTROY,
        )
    
    def create_s3_bucket(self, vpc: ec2.Vpc):
        # Create s3 bucket to store data
        bucket = s3.CfnBucket(self, "amzn-s3-slotify-sagemaker", bucket_name="amzn-s3-slotify-sagemaker")
        
        # allow s3 to be accessed by the vpc
        vpc.add_gateway_endpoint(
            id="S3", 
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )
        
        # Allow access to the s3 bucket
        s3.CfnAccessPoint(
            self,
            "s3_access",
            bucket=bucket.bucket_name, 
            vpc_configuration=s3.CfnAccessPoint.VpcConfigurationProperty(
                vpc_id=vpc.vpc_id
            )
        )
        
        return bucket
    
    def create_sagemaker(self, vpc: ec2.Vpc, sg: ec2.SecurityGroup):
        # Create sagemaker role
        role = iam.Role(
            self,
            "SagemakerCDKRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSageMakerFullAccess"
                ), iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSageMakerNotebooksServiceRolePolicy"
                ),  iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonS3FullAccess"
                )
            ],
        )
        
        role.add_to_policy(iam.PolicyStatement(
            actions=["iam:GetRole"],
            resources=[role.role_arn]
        ))
        
    
        # Create sagemaker notebook
        sagemaker.CfnNotebookInstance(self, "SlotifyNotebookInstance",
                                instance_type="ml.t2.medium",
                                role_arn=role.role_arn,
                                default_code_repository="https://github.com/SlotifyApp/ai.git",
                                security_group_ids=[sg.unique_id],
                                subnet_id=vpc.select_subnets(subnet_type=ec2.SubnetType.PUBLIC).subnet_ids[0]
                            )