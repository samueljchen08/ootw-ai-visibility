"""Split queries.json into agent batches and emit filled prompts."""
import json, os, sys, math

def make_batches(queries, size=8):
    core = [q for q in queries if q["tier"] == "core"]
    rest = [q for q in queries if q["tier"] != "core"]
    n = math.ceil(len(queries) / size)
    batches = [[] for _ in range(n)]
    for i, q in enumerate(core + rest):
        batches[i % n].append(q)
    return batches

def main(size=8):
    with open("queries.json") as f:
        queries = json.load(f)["queries"]
    with open("agents/answer-engine.md") as f:
        template = f.read()
    os.makedirs("results/simulated", exist_ok=True)
    for i, batch in enumerate(make_batches(queries, int(size)), 1):
        inp = f"results/simulated/batch-{i}.input.json"
        with open(inp, "w") as f:
            json.dump(batch, f, indent=2)
        prompt = template.replace("{{QUERIES_JSON}}", json.dumps(batch, indent=2)).replace(
            "{{OUTPUT_PATH}}", os.path.abspath(f"results/simulated/batch-{i}.json"))
        with open(f"results/simulated/batch-{i}.prompt.md", "w") as f:
            f.write(prompt)
        print(f"batch {i}: {len(batch)} queries -> results/simulated/batch-{i}.prompt.md")

if __name__ == "__main__":
    main(*sys.argv[1:])
