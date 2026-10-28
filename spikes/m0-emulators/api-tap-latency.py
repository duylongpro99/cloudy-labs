"""Measures the latency api-tap adds: N identical boto3 calls direct vs through the tap.
Usage: uv run --with boto3 python api-tap-latency.py [n]"""
import statistics, sys, time
import boto3

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200


def bench(endpoint):
    ec2 = boto3.client("ec2", endpoint_url=endpoint, region_name="us-east-1",
                       aws_access_key_id="test", aws_secret_access_key="test")
    ec2.describe_vpcs()  # warm the connection pool
    samples = []
    for _ in range(N):
        t = time.perf_counter(); ec2.describe_vpcs(); samples.append((time.perf_counter() - t) * 1000)
    samples.sort()
    return statistics.median(samples), samples[int(N * 0.95)]


d50, d95 = bench("http://localhost:4566")
t50, t95 = bench("http://localhost:4580")
print(f"describe_vpcs x{N}: direct p50={d50:.2f}ms p95={d95:.2f}ms | tap p50={t50:.2f}ms p95={t95:.2f}ms "
      f"| added p50={t50 - d50:.2f}ms p95={t95 - d95:.2f}ms")
