# =============================================================================
# Cloud SQL — pieza real de GCP para el laboratorio integrador U3 (módulo A.4)
#
# El cluster bajo prueba sigue siendo el kubeadm on-prem (D-01 del diseño de
# U3): esta instancia no reemplaza nada del cluster, solo le da a data-service
# un backend gestionado real al que llegar por Cloud SQL Auth Proxy.
#
# Corrección respecto al diseño original: el kubeadm de Bogotá no tiene VPN ni
# Interconnect hacia GCP, así que "sin IP pública" (Private IP / Private
# Service Connect) no es alcanzable desde ahí. Cloud SQL Auth Proxy no depende
# de que la IP esté en una allowlist — autentica con IAM + certificados
# efímeros por instancia — así que ipv4_enabled=true aquí no reabre el mismo
# riesgo que exponer el puerto 5432 directamente (que es lo que sí habría que
# evitar). Por eso no se define `authorized_networks`: igual que con el SG de
# RDS, la IP de casa es dinámica y una allowlist fija se rompería sola.
# =============================================================================

resource "random_password" "data_service_db" {
  length  = 20
  special = false
}

resource "google_sql_database_instance" "data_service" {
  name                = "u3-data-service"
  database_version    = "POSTGRES_15"
  region              = var.region
  deletion_protection = false

  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL"
    disk_autoresize   = false
    disk_size         = 10
    disk_type         = "PD_HDD"

    backup_configuration {
      enabled = false
    }

    insights_config {
      query_insights_enabled = true
    }

    ip_configuration {
      ipv4_enabled = true
    }
  }
}

resource "google_sql_database" "appdb" {
  name     = "appdb"
  instance = google_sql_database_instance.data_service.name
}

resource "google_sql_user" "app" {
  name     = "app"
  instance = google_sql_database_instance.data_service.name
  password = random_password.data_service_db.result
}

# ---------- Service account para el Cloud SQL Auth Proxy ----------
# El cluster kubeadm es externo a GCP: no hay Workload Identity posible ahí
# (eso solo aplica a nodos de GKE, ver el otel-collector de main.tf). La única
# vía es una key de SA descargada y montada como Secret de k8s — el comando
# de creación de la key queda deliberadamente fuera de Terraform para no
# dejar la clave privada en el tfstate.
resource "google_service_account" "data_service_sql_client" {
  account_id   = "data-service-sql-client"
  display_name = "Cloud SQL Auth Proxy — data-service (U3 integrador)"
}

resource "google_project_iam_member" "sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.data_service_sql_client.email}"
}

# ---------- Outputs ----------
output "u3_db_password" {
  value     = random_password.data_service_db.result
  sensitive = true
}

output "u3_sql_connection_name" {
  description = "project:region:instance — lo que recibe el Cloud SQL Auth Proxy"
  value       = google_sql_database_instance.data_service.connection_name
}

output "u3_sql_public_ip" {
  value = google_sql_database_instance.data_service.public_ip_address
}

output "u3_sql_client_sa_email" {
  value = google_service_account.data_service_sql_client.email
}

output "u3_comando_crear_key_sa" {
  description = "Corre esto en la Mac (necesita gcloud autenticado) para bajar la key de la SA"
  value       = "gcloud iam service-accounts keys create ~/data-service-gcp-sa-key.json --iam-account=${google_service_account.data_service_sql_client.email}"
}

output "u3_comando_crear_secret_k8s" {
  description = "Corre esto en la Mac (necesita kubectl apuntando al cluster kubeadm) después del comando anterior"
  value       = "kubectl create secret generic data-service-gcp-sql -n otel-lab --from-file=sa-key.json=$HOME/data-service-gcp-sa-key.json --from-literal=db-password=$(terraform output -raw u3_db_password)"
}
