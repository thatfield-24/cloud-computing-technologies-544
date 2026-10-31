"""Shared fixtures. Unit tests use fake settings, integration tests use your real .env."""
import os
from pathlib import Path
import pytest

from stack.clients import AwsClients
from stack.config import Settings
from stack.outputs import StackOutputs

ROOT = Path(__file__).resolve().parent.parent

FAKE_VALUES = {
    "AWS_REGION": "us-east-2", "AMI_ID": "ami-12345678", "KEY_NAME": "test-key",
    "INSTANCE_TYPE": "t3.micro", "BUCKET_NAME": "unit-test-bucket-12345",
    "APP_SECURITY_GROUP_ID": "sg-placeholder",
    "UPLOADER_ROLE_NAME": "t-uploader-role", "UPLOADER_PROFILE_NAME": "t-uploader-profile",
    "UPLOADER_LT_NAME": "t-uploader-lt", "UPLOADER_TG_NAME": "t-uploader-tg",
    "UPLOADER_ASG_NAME": "t-uploader-asg", "UPLOADER_LISTENER_PORT": "8080",
    "VIEWER_ROLE_NAME": "t-viewer-role", "VIEWER_PROFILE_NAME": "t-viewer-profile",
    "VIEWER_LT_NAME": "t-viewer-lt", "VIEWER_TG_NAME": "t-viewer-tg",
    "VIEWER_ASG_NAME": "t-viewer-asg", "VIEWER_LISTENER_PORT": "8081",
    "ALB_NAME": "t-alb", "ALB_SG_NAME": "t-alb-sg",
    "AZ_A": "us-east-2a", "AZ_B": "us-east-2b", "RECOVERY_SLO_SECONDS": "180",
    "DB_INSTANCE_ID": "itmo-444-544-weather-db", "DB_NAME": "weather", "DB_USER": "weatherapp",
    "DB_SG_NAME": "itmo-444-544-weather-db-sg", "DB_SUBNET_GROUP_NAME": "itmo-444-544-weather-db-subnets",
    "DB_PASSWORD_PARAM": "/itmo-444-544/db-password", "CACHE_SECONDS": "600", "GEMINI_PARAM_NAME": "/itmo-444-544/gemini-api-key",
    "GEMINI_MODEL": "gemini-3.1-flash-lite", "KEY_CACHE_SECONDS": "60", "CONTACT_EMAIL": "student@example.com", "RECOVERY_SLO_SECONDS": "180",
}

def load_env_file(filepath):
    """Reads key-value pairs from .env style files into os.environ if present."""
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip("'\"")

@pytest.fixture(scope="session", autouse=True)
def setup_unit_test_credentials_and_env():
    """Sets dummy AWS credentials for moto unit tests and loads stack environment variables."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = os.environ.get("AWS_REGION", "us-east-1")

    load_env_file(ROOT / ".env")
    load_env_file(ROOT / "stack_outputs.env")
    load_env_file(ROOT / "db_outputs.env")

@pytest.fixture
def fake_settings(tmp_path):
    """Settings pointing at fake app folders for unit testing."""
    for name in ("weather-app", "advisor-app"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "app.js").write_text(f"console.log('{name}');\n")
        (folder / "package.json").write_text('{"name": "%s"}\n' % name)
    return Settings.from_values(FAKE_VALUES, base_dir=tmp_path)

@pytest.fixture(scope="session")
def settings():
    return Settings.from_file(ROOT / ".env")


@pytest.fixture(scope="session")
def aws(settings):
    return AwsClients.create(settings.region)


@pytest.fixture(scope="session")
def outputs():
    try:
        return StackOutputs.load(ROOT)
    except FileNotFoundError:
        pytest.skip("stack_outputs.env not found. Deploy stack before running integration tests.")