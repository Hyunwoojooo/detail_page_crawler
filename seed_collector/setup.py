from setuptools import find_packages, setup


setup(
    name="seed-collector",
    version="0.1.0",
    description="Seed URL collector for e-commerce category pages",
    long_description="Seed URL collector for e-commerce category pages",
    long_description_content_type="text/plain",
    author="Prompt Shopping",
    python_requires=">=3.9",
    packages=find_packages(include=["seed_collector", "seed_collector.*"]),
    install_requires=[
        "httpx>=0.27.0",
        "pydantic>=2.6.0",
        "beautifulsoup4>=4.12.0",
    ],
    extras_require={
        "test": ["pytest>=8.0.0"],
    },
    entry_points={
        "console_scripts": [
            "seed-collector=seed_collector.cli:main",
        ]
    },
)
