from setuptools import setup, find_packages

setup(
    name="netkvmswitch",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "pynput",
        # Add other dependencies as they are identified
    ],
    entry_points={
        'console_scripts': [
            'netkvm_server=central_hub.server:main',
            'netkvm_agent=source_agent.client:main',
        ],
    },
)