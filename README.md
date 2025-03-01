# infra

This repo contains infrastructure as code. Currently, contains:

- AWS CDK code for provisioning AWS infra
- Terraform code for Microsoft Entra app registration

## Setup

- Make sure to first configure [AWS CDK along with any prequisites](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html).
  Note: configure default region to be 'eu-west-2' for aws cli

- Make sure to install [terraform](https://developer.hashicorp.com/terraform/install)

- Install [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-linux?pivots=apt), this is needed
  for terraform

- Login with azure-cli:

```bash
az login --allow-no-subscriptions
```

## Terraform

```bash
terraform plan # Dry-run, see what tf needs to do
terraform apply # Apply tf script
terraform output client_secret # view microsoft client secret
```
