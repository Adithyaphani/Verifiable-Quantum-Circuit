"""Toffoli count per @stage tag of a kickmix circuit."""
import collections, os, sys, tempfile
import kickmix as km

def breakdown(c):
    with tempfile.NamedTemporaryFile("r", suffix=".kmx", delete=False) as f: name = f.name
    c.to_file(name, format="kmx"); txt = open(name).read(); os.unlink(name)
    cur = "pre"; tof = collections.Counter(); rot = collections.Counter()
    for ln in txt.splitlines():
        if ln.startswith('INFO_TAG "@stage:'):
            cur = ln.split(":")[1].rstrip('"')
        elif ln.split(" ", 1)[0] in ("CCX", "CCZ", "CSWAP"):
            tof[cur] += 1
        elif ln.startswith("Z_POW"):
            rot[cur] += 1
    return tof, rot

if __name__ == "__main__":
    t, r = breakdown(km.Circuit.from_file(sys.argv[1]))
    for k in t: print(f"{k:>12}: {t[k]:6d} toffoli")
    print("total", sum(t.values()), "z_pow", dict(r))
