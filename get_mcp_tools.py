import subprocess
import json
import os

def get_tools(cmd, args, env_vars=None):
    env = os.environ.copy()
    if env_vars:
        for k, v in env_vars.items():
            env[k] = v
            
    try:
        p = subprocess.Popen([cmd] + args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        
        # Send init
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        }
        p.stdin.write(json.dumps(init_req) + "\n")
        p.stdin.flush()
        
        # process jsonrpc messages (since server might send logs/notifications before standard response)
        # We need a loop to wait for id: 2
        
        # We first send initialized notification
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        p.stdin.write(json.dumps(init_notif) + "\n")
        p.stdin.flush()
        
        tools_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        p.stdin.write(json.dumps(tools_req) + "\n")
        p.stdin.flush()
        
        print(f"\n# {args[0] if args else cmd}")
        
        for idx in range(20): # read up to 20 lines
            line = p.stdout.readline()
            if not line: break
            try:
                data = json.loads(line)
                if data.get("id") == 2:
                    if "result" in data and "tools" in data["result"]:
                        for t in data["result"]["tools"]:
                            print(f"- **{t['name']}**: {t.get('description', '')}")
                    elif "error" in data:
                        print("Error:", data["error"])
                    break
            except:
                pass
        p.terminate()
    except Exception as e:
        print("Failed to run:", e)

# Gurufocus
import json
with open(".mcp.json", "r") as f:
    config = json.load(f)

for name, srv in config["mcpServers"].items():
    get_tools(srv["command"], srv["args"], srv.get("env", {}))
