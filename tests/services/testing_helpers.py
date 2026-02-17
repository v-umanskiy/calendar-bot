import json
import types
import sys
import os

class _DummyBody:
    def read(self):
        return b""


class _DummyS3Client:
    def put_object(self, **_kwargs):
        pass

    def get_object(self, **_kwargs):
        return {"Body": _DummyBody()}

    def delete_objects(self, **_kwargs):
        pass

    def get_secret_value(self, **_kwargs):
        return {
            "SecretString": json.dumps(
                {
                    "OPENAI_API_KEY": "dummy",
                    "GEMINI_API_KEY": "dummy",
                    "PINECONE_API_KEY": "dummy",
                    "TELEGRAM_BOT_TOKEN": "dummy",
                    "WEBHOOK_SECRET": "dummy",
                }
            )
        }


class _DummyBatchWriter:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def delete_item(self, **_kwargs):
        pass


class _DummyTable:
    def put_item(self, Item):
        pass

    def query(self, **_kwargs):
        return {"Items": []}

    def batch_writer(self):
        return _DummyBatchWriter()


class _DummyDynamoResource:
    def Table(self, _name):
        return _DummyTable()


class _DummyKey:
    def __init__(self, *_args, **_kwargs):
        pass

    def eq(self, value):
        return value


_dummy_boto3 = types.ModuleType("boto3")
_dummy_boto3.client = lambda service_name: _DummyS3Client()
_dummy_boto3.resource = lambda resource_name: _DummyDynamoResource()

_dummy_dynamodb = types.ModuleType("boto3.dynamodb")
_dummy_conditions = types.ModuleType("boto3.dynamodb.conditions")
_dummy_conditions.Key = _DummyKey
_dummy_dynamodb.conditions = _dummy_conditions

class _DummyPineconeIndex:
    def query(self, **_kwargs):
        return {"matches": []}


class _DummyPinecone:
    def __init__(self, **_kwargs):
        pass

    def Index(self, _name):
        return _DummyPineconeIndex()


class _DummyGenerativeResponse:
    def __init__(self, text: str = ""):
        self.text = text


class _DummyGenaiModels:
    def generate_content(self, **_kwargs):
        return _DummyGenerativeResponse()


_dummy_pinecone = types.ModuleType("pinecone")
_dummy_pinecone.Pinecone = _DummyPinecone

class _DummyGenaiClient:
    def __init__(self, **_kwargs):
        self.models = _DummyGenaiModels()


_dummy_genai = types.ModuleType("google.genai")
_dummy_genai.Client = _DummyGenaiClient

_dummy_google_module = types.ModuleType("google")
_dummy_google_api_core = types.ModuleType("google.api_core")
_dummy_google_api_core_exceptions = types.ModuleType("google.api_core.exceptions")
_dummy_google_module.__path__ = []
_dummy_google_api_core.__path__ = []


class _DummyGoogleApiError(Exception):
    pass


class _DummyResourceExhausted(_DummyGoogleApiError):
    pass


class _DummyTooManyRequests(_DummyGoogleApiError):
    pass


_dummy_google_api_core_exceptions.ResourceExhausted = _DummyResourceExhausted
_dummy_google_api_core_exceptions.TooManyRequests = _DummyTooManyRequests
_dummy_google_api_core.exceptions = _dummy_google_api_core_exceptions

_dummy_google_module.genai = _dummy_genai
_dummy_google_module.api_core = _dummy_google_api_core

os.environ.setdefault("GEMINI_API_KEY", "dummy")
os.environ.setdefault("PINECONE_API_KEY", "dummy")
os.environ.setdefault("OPENAI_API_KEY", "dummy")

sys.modules.setdefault("boto3", _dummy_boto3)
sys.modules.setdefault("boto3.dynamodb", _dummy_dynamodb)
sys.modules.setdefault("boto3.dynamodb.conditions", _dummy_conditions)
sys.modules.setdefault("pinecone", _dummy_pinecone)
sys.modules.setdefault("google.genai", _dummy_genai)
sys.modules.setdefault("google", _dummy_google_module)
sys.modules.setdefault("google.api_core", _dummy_google_api_core)
sys.modules.setdefault("google.api_core.exceptions", _dummy_google_api_core_exceptions)
