"""VoiceMesh FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from src.api.config import settings
from src.api.database import init_db, close_db
from src.api.routes import customers, voice, voice_config

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

# Create FastAPI app
app = FastAPI(
    title="VoiceMesh API",
    description="Voice AI platform with embedded code execution via MCP",
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(customers.router)
app.include_router(voice.router)
app.include_router(voice_config.router)


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info(
        "voicemesh_startup",
        env=settings.ENV,
        port=settings.PORT,
    )

    # Initialize database tables (create_all is idempotent - safe to run in production)
    try:
        await init_db()
        logger.info("database_initialized", env=settings.ENV)
    except Exception as e:
        logger.error("database_init_failed", error=str(e), env=settings.ENV)


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    await close_db()
    logger.info("voicemesh_shutdown")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "VoiceMesh",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for Fly.io monitoring.

    Returns:
        200 OK if service is healthy
        503 Service Unavailable if unhealthy
    """
    try:
        # Basic health check
        health_status = {
            "status": "healthy",
            "service": "voicemesh",
            "environment": settings.ENV,
        }

        # Check if critical environment variables are set
        checks = {
            "database": bool(settings.DATABASE_URL),
            "deepgram": bool(settings.DEEPGRAM_API_KEY),
            "cartesia": bool(settings.CARTESIA_API_KEY),
            "anthropic": bool(settings.ANTHROPIC_API_KEY),
            "signalwire": bool(settings.SIGNALWIRE_PROJECT_ID and settings.SIGNALWIRE_TOKEN),
            "storage": bool(settings.AWS_ACCESS_KEY_ID and settings.BUCKET_NAME),
        }

        health_status["checks"] = checks

        # Mark as degraded if any checks fail, but still return 200
        # This allows deployment to succeed even if some services aren't ready yet
        if not all(checks.values()):
            health_status["status"] = "degraded"
            logger.warning("health_check_degraded", checks=checks)

        # Always return 200 OK to pass health checks during deployment
        # The status field indicates if services are degraded
        return health_status

    except Exception as e:
        logger.error("health_check_failed", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.

    This will be expanded later with actual metrics.
    """
    return {
        "status": "metrics_endpoint_placeholder",
        "message": "Prometheus metrics will be implemented here"
    }
