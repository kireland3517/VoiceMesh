#!/usr/bin/env python
"""Test environment variables and API keys."""

import os
from src.api.config import settings

print('=== API Key Status ===')
print(f'DEEPGRAM_API_KEY: {"✓ SET" if settings.DEEPGRAM_API_KEY else "✗ MISSING"} ({len(settings.DEEPGRAM_API_KEY) if settings.DEEPGRAM_API_KEY else 0} chars)')
print(f'CARTESIA_API_KEY: {"✓ SET" if settings.CARTESIA_API_KEY else "✗ MISSING"} ({len(settings.CARTESIA_API_KEY) if settings.CARTESIA_API_KEY else 0} chars)')
print(f'ANTHROPIC_API_KEY: {"✓ SET" if settings.ANTHROPIC_API_KEY else "✗ MISSING"} ({len(settings.ANTHROPIC_API_KEY) if settings.ANTHROPIC_API_KEY else 0} chars)')
print(f'DAILY_API_KEY: {"✓ SET" if settings.DAILY_API_KEY else "✗ MISSING"} ({len(settings.DAILY_API_KEY) if settings.DAILY_API_KEY else 0} chars)')
print(f'SIGNALWIRE_PROJECT_ID: {"✓ SET" if settings.SIGNALWIRE_PROJECT_ID else "✗ MISSING"}')
print(f'SIGNALWIRE_TOKEN: {"✓ SET" if settings.SIGNALWIRE_TOKEN else "✗ MISSING"}')

print('\n=== Environment Debug ===')
print(f'ENV: {settings.ENV}')
print(f'DATABASE_URL set: {"✓" if settings.DATABASE_URL else "✗"}')

# Show first 8 characters of each API key for debugging
if settings.DEEPGRAM_API_KEY:
    print(f'DEEPGRAM starts with: {settings.DEEPGRAM_API_KEY[:8]}...')
if settings.CARTESIA_API_KEY:
    print(f'CARTESIA starts with: {settings.CARTESIA_API_KEY[:8]}...')
if settings.DAILY_API_KEY:
    print(f'DAILY starts with: {settings.DAILY_API_KEY[:8]}...')