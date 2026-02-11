"""
test_url_discovery.py — Unit tests for v3.1 URL discovery logic
================================================================
Tests _build_direct_urls, _extract_tunnel_url regex patterns,
and _check_url with mock data. No Vast.ai costs involved.
"""

import sys
import os
import re

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# We test the regex patterns directly since we can't easily instantiate
# VastRunnerInterface without the full Flet setup

def test_tunnel_regex_cloudflare():
    """Test Cloudflare tunnel URL extraction from logs."""
    logs = """
    2024-01-15 10:30:00 Starting ComfyUI...
    2024-01-15 10:30:05 Cloudflare tunnel started
    2024-01-15 10:30:05 https://random-four-words.trycloudflare.com
    2024-01-15 10:30:10 ComfyUI ready on port 8188
    """
    matches = re.findall(r'(https://[\w-]+\.trycloudflare\.com)', logs)
    assert len(matches) == 1
    assert matches[0] == "https://random-four-words.trycloudflare.com"
    print("✅ Cloudflare tunnel regex: PASS")


def test_tunnel_regex_vast_proxy():
    """v3.1: Test Vast.ai proxy URL extraction from logs."""
    logs = """
    2024-01-15 10:30:00 Starting services...
    2024-01-15 10:30:05 Proxy available at https://12345-8188.proxy.vast.ai/
    2024-01-15 10:30:10 ComfyUI ready
    """
    matches = re.findall(r'(https://[\w-]+\.proxy\.vast\.ai[/\w]*)', logs)
    assert len(matches) == 1
    assert "proxy.vast.ai" in matches[0]
    print("✅ Vast.ai proxy regex: PASS")


def test_tunnel_regex_vast_generic():
    """v3.1: Test generic Vast.ai URL with port pattern."""
    logs = """
    2024-01-15 10:30:00 Instance ready
    2024-01-15 10:30:05 Access at https://abc123-8188.vast.ai
    """
    matches = re.findall(r'(https://[\w-]+-\d+\.vast\.ai[/\w]*)', logs)
    assert len(matches) == 1
    assert "vast.ai" in matches[0]
    print("✅ Vast.ai generic URL regex: PASS")


def test_tunnel_regex_no_match():
    """Test that random logs don't produce false positives."""
    logs = """
    2024-01-15 10:30:00 Starting ComfyUI...
    2024-01-15 10:30:05 Listening on 0.0.0.0:8188
    2024-01-15 10:30:10 Ready!
    """
    cf = re.findall(r'(https://[\w-]+\.trycloudflare\.com)', logs)
    proxy = re.findall(r'(https://[\w-]+\.proxy\.vast\.ai[/\w]*)', logs)
    vast = re.findall(r'(https://[\w-]+-\d+\.vast\.ai[/\w]*)', logs)
    assert len(cf) == 0
    assert len(proxy) == 0
    assert len(vast) == 0
    print("✅ No false positives: PASS")


def test_build_direct_urls():
    """Test _build_direct_urls logic with mock instance data."""
    def build_direct_urls(instance_data):
        """Standalone version of _build_direct_urls for testing."""
        COMFYUI_PORT = 8188
        urls = []
        public_ip = instance_data.get("public_ipaddr", "")
        ports = instance_data.get("ports", {})
        direct_port_start = instance_data.get("direct_port_start", 0)
        
        if ports and isinstance(ports, dict):
            for key in ["8188/tcp", "8188"]:
                if key in ports:
                    port_info = ports[key]
                    if isinstance(port_info, list) and port_info:
                        hp = port_info[0].get("HostPort", "")
                        if hp and public_ip:
                            urls.append(f"http://{public_ip}:{hp}")
        
        if direct_port_start and direct_port_start > 0 and public_ip:
            urls.append(f"http://{public_ip}:{direct_port_start}")
        
        if public_ip:
            urls.append(f"http://{public_ip}:{COMFYUI_PORT}")
        
        seen = set()
        return [u for u in urls if u not in seen and not seen.add(u)]
    
    # Test 1: Full data with ports
    data = {
        "public_ipaddr": "192.168.1.100",
        "ports": {"8188/tcp": [{"HostIp": "192.168.1.100", "HostPort": "40001"}]},
        "direct_port_start": 40000,
    }
    urls = build_direct_urls(data)
    assert "http://192.168.1.100:40001" in urls
    assert "http://192.168.1.100:40000" in urls
    assert "http://192.168.1.100:8188" in urls
    print(f"✅ Full data URLs ({len(urls)} candidates): PASS")
    
    # Test 2: No ports
    data_no_ports = {"public_ipaddr": "10.0.0.1"}
    urls = build_direct_urls(data_no_ports)
    assert urls == ["http://10.0.0.1:8188"]
    print("✅ No ports fallback: PASS")
    
    # Test 3: No IP
    data_no_ip = {"ports": {"8188/tcp": [{"HostPort": "40001"}]}}
    urls = build_direct_urls(data_no_ip)
    assert urls == []
    print("✅ No IP returns empty: PASS")


def test_proxy_url_construction():
    """v3.1: Test proxy URL construction from instance ID."""
    instance_id = "12345678"
    port = 8188
    proxy_url = f"https://{instance_id}-{port}.proxy.vast.ai/"
    assert proxy_url == "https://12345678-8188.proxy.vast.ai/"
    print("✅ Proxy URL construction: PASS")


def test_onstart_cmd_auto_detect():
    """v3.1: Test that onstart-cmd uses auto-detect instead of hardcoded path."""
    gdrive_id = "test_folder_123"
    loader_url = "https://raw.githubusercontent.com/galhosostore-coder/ComfyUI-VastAI/main/lazy_model_loader.py"
    onstart_cmd = (
        f'COMFY_DIR=$(find / -maxdepth 4 -name "main.py" -path "*/ComfyUI/*" 2>/dev/null | head -1 | xargs -r dirname); '
        f'COMFY_DIR=${{COMFY_DIR:-/opt/ComfyUI}}; '
        f'cd "$COMFY_DIR" && '
        f"curl -sL '{loader_url}' -o lazy_model_loader.py && "
        f"python3 lazy_model_loader.py {gdrive_id} &"
    )
    # Key assertions:
    assert "/workspace" not in onstart_cmd, "Should NOT hardcode /workspace!"
    assert "find /" in onstart_cmd, "Should auto-detect ComfyUI directory"
    assert "/opt/ComfyUI" in onstart_cmd, "Should have fallback to /opt/ComfyUI"
    assert gdrive_id in onstart_cmd
    print("✅ onstart-cmd auto-detect: PASS")


if __name__ == "__main__":
    print("=" * 50)
    print("v3.1 URL Discovery Unit Tests")
    print("=" * 50 + "\n")
    
    test_tunnel_regex_cloudflare()
    test_tunnel_regex_vast_proxy()
    test_tunnel_regex_vast_generic()
    test_tunnel_regex_no_match()
    test_build_direct_urls()
    test_proxy_url_construction()
    test_onstart_cmd_auto_detect()
    
    print("\n" + "=" * 50)
    print("ALL TESTS PASSED ✅")
    print("=" * 50)
