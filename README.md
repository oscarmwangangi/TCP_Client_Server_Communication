### 📂 Project Structure

**Root Directory**
- `config.ini` - Server configuration file
- `client.py` - CLI client to query the server
- `server.py` - Main TCP server implementation 
- `200k.txt` - Sample data file for testing
- `search.py` - Search algorithm implementations
- `service_setup.sh` - Systemd service installer
- `server.log` - Log file generated by the server
- `ssl_utils.py` - SSL/TLS helper functions
- `requirements.txt` - Python dependencies
- `README.md` - Setup and usage documentation

**benchmarks/** (Performance testing)
- `benchmark_report.pdf` - PDF report of algorithm comparisons
- `performance_comparison.png` - Visual graphs of benchmark results
- `performance_report.png` - Visual graphs of benchmark report
- `raw_benchmark_data.csv` - Csv report of algorithm comparisons
- `speed_test.py` - Script to test search algorithm speeds
- 

**tests/** (Unit and integration tests)
- `test_server.py` - Tests for server.py
- `test_search.py` - Tests for search.py 
- `test_ssl_utils.py` - Tests for ssl_utils.py



## 📋 Requirements
- Linux (Ubuntu/Debian/CentOS)
- Python 3.8+
- pip package manager

### 🚀 Manual Installation

## 1. Download and Extract
1. Download the project ZIP 
2. Extract to your preferred location:
   ```bash
   unzip tcp_search_server.zip -d ~/tcp_search_server
   cd ~/tcp_search_server
   ```

## 2. Install Dependencies
  ```bash
  pip install -r requirements.txt
  ```

## 3. Configuration
[PATHS]
linuxpath=200k.txt  

[SERVER]
port = 5555                
reread_on_query = False    
[SSL]
certfile=cert.pem
keyfile=key.pem

## 4. ⚡Quick Testing
Open two terminals in the project directory:

1. Run the server in one terminal:
   ```bash
   python3 server.py
   ```

2. Terminal 2 run Client:
    ```bash
    python3 client.py "your_search_string"
    ```

## 5. 🧪Performing Tests
Run the test suite with coverage report:
  ```bash
   python -m pytest -v --cov=../ --cov-report=html
   ```

  # Individual test modules:
   1. Server functionality tests
      ```bash
      pytest tests/test_server.py -v
      ```
   2. Search algorithm tests 
      ```bash
      pytest tests/test_search.py -v
      ```
   3. Client functionality tests
      ```bash
      pytest tests/test_client.py -v
      ```

## 6. 📊Benchmarking
- This will run a simple benchmark to measure the server's response time for a given search query.
  ```bash
  cd benchmarks
  python3 speed_test.py
  ```
- opening the pdf
  ```bash
    xdg-open benchmarks/benchmarks/benchmark_report.pdf
  ```

## 7. 🔧Production Deployment
  1. Systemd Service Setup
      ```bash
      chmod +x service_setup.sh  
      sudo ./service_setup.sh
      ```
  2. Verify Installation
      ``` bash
      sudo systemctl status tcpsearchserver
      ```
  3. Test Connectivity
      ```
      python3 client.py "test_query" --port 5555
      ```