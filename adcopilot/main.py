from fastapi import FastAPI


def create_app() -> FastAPI:
    application = FastAPI(title="AdCopilot", version="0.1.0")
    return application


app = create_app()
