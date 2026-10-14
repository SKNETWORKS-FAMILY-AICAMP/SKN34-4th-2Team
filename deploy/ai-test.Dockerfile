FROM lms-ai:ci
RUN pip install --no-cache-dir 'pytest>=8,<9' 'pytest-asyncio>=0.24,<1' 'httpx>=0.27,<1'
