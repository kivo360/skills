/**
 * Chroma vector store wrapper for the skill embeddings.
 *
 * Chroma is a daemon-only optimization: when `toolbelt skills serve`
 * is running, it spawns Chroma as a child process and the daemon's
 * `/match` endpoint queries it via HNSW. When the daemon is down, the
 * matcher falls back to looping cosine over the JSON cache.
 *
 * Why not use Chroma in every CLI invocation? Because Chroma needs a
 * server (the JS client has no in-memory mode) and ~3 s to boot —
 * intolerable for a 50 ms hook. The JSON file is the durable
 * source-of-truth dump; Chroma is the query index.
 *
 * Distance: configured with `space="cosine"`, so Chroma returns
 * `distance = 1 - cos`. We convert back to cos for ranking so the
 * blend math in hybrid-matcher.ts stays unchanged.
 */

import { ChromaClient } from "chromadb";

export interface ChromaConnectOpts {
  host?: string;
  port?: number;
  collection?: string;
}

export interface SkillMetadata {
  tier: string;
  description: string;
  mtime: number;
  source: string;
}

export interface ChromaQueryHit {
  name: string;
  cosine: number;
  metadata: SkillMetadata;
}

const DEFAULT_HOST = "localhost";
const DEFAULT_PORT = 8765;
const DEFAULT_COLLECTION = "skills";

export class ChromaSkillStore {
  private constructor(
    private client: ChromaClient,
    private collection: Awaited<ReturnType<ChromaClient["getOrCreateCollection"]>>,
    public readonly name: string
  ) {}

  static async connect(opts: ChromaConnectOpts = {}): Promise<ChromaSkillStore> {
    const host = opts.host ?? DEFAULT_HOST;
    const port = opts.port ?? DEFAULT_PORT;
    const collectionName = opts.collection ?? DEFAULT_COLLECTION;

    const client = new ChromaClient({ host, port, ssl: false });
    // Probe — heartbeat will throw if Chroma isn't reachable.
    await client.heartbeat();

    const collection = await client.getOrCreateCollection({
      name: collectionName,
      metadata: { "hnsw:space": "cosine" },
    });

    return new ChromaSkillStore(client, collection, collectionName);
  }

  static async ping(opts: ChromaConnectOpts = {}): Promise<boolean> {
    try {
      const client = new ChromaClient({
        host: opts.host ?? DEFAULT_HOST,
        port: opts.port ?? DEFAULT_PORT,
        ssl: false,
      });
      await Promise.race([
        client.heartbeat(),
        new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 800)),
      ]);
      return true;
    } catch {
      return false;
    }
  }

  async upsert(
    items: Array<{ name: string; vector: number[]; metadata: SkillMetadata }>
  ): Promise<void> {
    if (items.length === 0) return;
    // Chroma JS SDK takes parallel arrays. Limit batch size to keep
    // any single HTTP request small and avoid hitting upload caps.
    const BATCH = 64;
    for (let i = 0; i < items.length; i += BATCH) {
      const chunk = items.slice(i, i + BATCH);
      await this.collection.upsert({
        ids: chunk.map((c) => c.name),
        embeddings: chunk.map((c) => c.vector),
        metadatas: chunk.map((c) => ({ ...c.metadata })),
      });
    }
  }

  async query(
    vector: number[],
    k: number,
    opts: { tiers?: string[] } = {}
  ): Promise<ChromaQueryHit[]> {
    const where = opts.tiers && opts.tiers.length > 0 ? { tier: { $in: opts.tiers } } : undefined;
    const res = await this.collection.query({
      queryEmbeddings: [vector],
      nResults: k,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      where: where as any, // chromadb's Where type is a union that doesn't accept structural records cleanly
    });

    const ids = (res.ids?.[0] ?? []) as string[];
    const distances = (res.distances?.[0] ?? []) as number[];
    const metadatas = (res.metadatas?.[0] ?? []) as Array<Record<string, unknown>>;

    const out: ChromaQueryHit[] = [];
    for (let i = 0; i < ids.length; i++) {
      const meta = metadatas[i] ?? {};
      out.push({
        name: ids[i],
        cosine: 1 - (distances[i] ?? 1),
        metadata: {
          tier: String(meta.tier ?? "B"),
          description: String(meta.description ?? ""),
          mtime: Number(meta.mtime ?? 0),
          source: String(meta.source ?? ""),
        },
      });
    }
    return out;
  }

  async deleteMissing(validNames: Set<string>): Promise<number> {
    // Pull all IDs, delete the ones no longer in the index. Keeps
    // Chroma in sync when skills are removed/renamed.
    const all = await this.collection.get();
    const ids = (all.ids ?? []) as string[];
    const toDelete = ids.filter((id) => !validNames.has(id));
    if (toDelete.length === 0) return 0;
    await this.collection.delete({ ids: toDelete });
    return toDelete.length;
  }

  async count(): Promise<number> {
    return this.collection.count();
  }

  async clear(): Promise<void> {
    const all = await this.collection.get();
    const ids = (all.ids ?? []) as string[];
    if (ids.length > 0) await this.collection.delete({ ids });
  }
}
