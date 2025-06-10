# NetKVMSwitch

A software-based KVM (Keyboard, Video, Mouse) solution allowing a central laptop to display video feeds from, and send keyboard/mouse inputs to, multiple source laptops over a local network. A Streamlit web UI on the central laptop will manage connections and switching.

## Project Structure

```
netkvmswitch/
├── src/
│   ├── central_hub/        # Server-side logic
│   ├── source_agent/       # Client-side logic
│   ├── common/             # Shared code (protocol, utils)
│   └── ui/                 # Streamlit UI application
├── tests/                  # Unit and integration tests
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── requirements.txt        # Python dependencies
├── setup.py                # Packaging script
├── README.md               # This file
└── .gitignore              # Files to ignore in git
```

## Setup and Installation

1.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Generate TLS Certificates:**
    Run the certificate generation script from the `netkvmswitch` directory:
    ```bash
    python generate_certs.py
    ```
    This will create a `certs` directory in the parent `CKVM` folder (i.e., `../certs/`) and populate it with the necessary CA, server, and client certificates and keys.

## Usage

1.  **Start the Central Hub (Server):**
    Navigate to the `src/central_hub` directory and run:
    ```bash
    python server.py
    ```

2.  **Start the Source Agent (Client) on each source machine:**
    Navigate to the `src/source_agent` directory and run:
    ```bash
    python client.py
    ```
    (You might need to configure the server IP in `client.py` if it's not running on localhost).

3.  **Access the UI:**
    (Details to be added once the Streamlit UI is implemented - likely involves running a Streamlit command from the `src/ui` directory).