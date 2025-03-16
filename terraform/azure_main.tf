terraform {
  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.1.0"
    }
  }
}

variable "HOMEPAGE_URL" {}
variable "REDIRECT_URI" {}

provider "azuread" {}

# Get current Azure AD client details
data "azuread_client_config" "current" {}

# Register the application
resource "azuread_application" "slotify" {
  display_name     = "Slotify"
  sign_in_audience = "AzureADMyOrg" #Only care about users in this tenant

  # Set up OAuth2 authentication
  web {
    homepage_url = "${var.HOMEPAGE_URL}"
    logout_url   = "${var.HOMEPAGE_URL}"
    redirect_uris = [
      "${var.REDIRECT_URI}"
    ]

    implicit_grant {
      access_token_issuance_enabled = true
      id_token_issuance_enabled     = true
    }
  }

  # API Permissions (Microsoft Graph)
  required_resource_access {
    resource_app_id = "00000003-0000-0000-c000-000000000000" # Microsoft Graph

    resource_access {
      id   = "37f7f235-527c-4136-accd-4a02d197296e" # openid
      type = "Scope"
    }

    resource_access {
      id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d" # User.Read
      type = "Scope"
    }

    resource_access {
      id   = "798ee544-9d2d-430c-a058-570e29e34338" # Calendars.Read
      type = "Role"
    }

    resource_access {
      id   = "465a38f9-76ea-45b9-9f34-9e8b0d4b0b42" # Calendars.Read
      type = "Scope"
    }

    resource_access {
      id   = "2b9c4092-424d-4249-948d-b43879977640" # Calendars.Read.Shared
      type = "Scope"
    }

    resource_access {
      id   = "ef54d2bf-783f-4e0f-bca1-3210c0444d99" # Calendars.ReadWrite
      type = "Role"
    }

    resource_access {
      id   = "1ec239c2-d7c9-4623-a91a-a9775856bb36" # Calendars.ReadWrite
      type = "Scope"
    }

    resource_access {
      id   = "12466101-c9b8-439a-8589-dd09ee67e8e9" # Calendars.ReadWrite.Shared
      type = "Scope"
    }

    resource_access {
      id   = "741f803b-c850-494e-b5df-cde7c675a1ca" # User.ReadWrite.All
      type = "Role"
    }
    resource_access {
      id   = "204e0828-b5ca-4ad8-b9f3-f32a958e7cc4" # User.ReadWrite.All
      type = "Scope"
    }

    resource_access {
      id   = "5f8c59db-677d-491f-a6b8-5f174b11ec1d" # Group.Read.All
      type = "Scope"
    }

    resource_access {
      id   = "4e46008b-f24c-477d-8fff-7bb4ec7aafe0" # Group.ReadWrite.All
      type = "Scope"
    }

    resource_access {
      id   = "913b9306-0ce1-42b8-9137-6a7df690a760" # Place.Read.All
      type = "Role"
    }
    resource_access {
      id   = "cb8f45a0-5c2e-4ea1-b803-84b870a7d7ec" # Place.Read.All
      type = "Scope"
    }
  }

  feature_tags {
    enterprise = true
    gallery    = true
  }
}

# Create a service principal for authentication
resource "azuread_service_principal" "slotify_sp" {
  client_id = azuread_application.slotify.client_id
}

# Create a client secret
resource "azuread_application_password" "slotify_secret" {
  application_id = azuread_application.slotify.id
  display_name   = "client_secret"
  end_date       = timeadd("2025-01-30T12:45:05Z", "10000h")
}

# Output values for use in NextAuth
output "client_id" {
  value = azuread_application.slotify.client_id
}

output "client_secret" {
  value     = azuread_application_password.slotify_secret.value
  sensitive = true
}

output "tenant_id" {
  value = data.azuread_client_config.current.tenant_id
}
