from __future__ import annotations

from setuptools import setup, find_packages

setup(
    name="deployflow",
    version="0.1.0",
    description="One-click build and publish for Godot and Unity games",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=["keyring>=24.0.0"],
    entry_points={
        "console_scripts": [
            "deployflow=deployflow.__main__:main",
        ],
    },
)
