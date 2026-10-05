import { useEffect, useState } from "react";
import { ArrowRight, BarChart3 } from "lucide-react";
import { api, type DatasetRanking, type Run } from "../api";

export default function RankingChart({
  runs,
  onNewRun,
}: {
  runs: Run[];
  onNewRun: () => void;
}) {
  const latestRun = runs[0];
  const effectiveId = latestRun?.id || "";
  const [ranking, setRanking] = useState<DatasetRanking | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!effectiveId) {
      setRanking(null);
      return;
    }
    const controller = new AbortController();
    setRanking(null);
    setLoading(true);
    setError("");
    api<DatasetRanking>(`/runs/${effectiveId}/dataset-ranking`, undefined, "GET", controller.signal)
      .then(setRanking)
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "無法載入排行榜");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [effectiveId]);

  useEffect(() => {
    if (!effectiveId || !ranking || ranking.is_final) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      api<DatasetRanking>(`/runs/${effectiveId}/dataset-ranking`, undefined, "GET", controller.signal)
        .then(setRanking)
        .catch(() => {
          if (!controller.signal.aborted) setError("排行榜暫時無法更新");
        });
    }, 10000);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [effectiveId, ranking?.is_final]);

  return (
    <section className="panel ranking-panel" aria-labelledby="ranking-title">
      <div className="section-head ranking-head">
        <div>
          <h2 id="ranking-title">模型排名 <span>MODEL RANKING</span></h2>
          <p>{ranking ? `同一題庫版本「${ranking.dataset_name}」，彙整各次測試的模型成績。` : "依同一份題庫的測試題目比較模型成績。"}</p>
        </div>
      </div>
      {!effectiveId ? (
        <div className="ranking-empty">
          <BarChart3 size={28} />
          <strong>完成第一場測試後，這裡會顯示模型排名。</strong>
          <button className="text-button" onClick={onNewRun}>建立測試 <ArrowRight size={14} /></button>
        </div>
      ) : loading && !ranking ? (
        <p className="ranking-message" role="status">正在載入排名…</p>
      ) : error && !ranking ? (
        <p className="ranking-message" role="alert">{error}</p>
      ) : ranking ? (
        <div className="ranking-content">
          {ranking.models.length === 0 && (
            <p className="ranking-note">目前沒有完成同一份題庫全部題目的測試紀錄。</p>
          )}
          {ranking.models.length > 0 && ranking.models.every((model) => model.graded === 0) && (
            <p className="ranking-note">這份題庫尚無可自動評分的回答；人工評分與 API 失敗不計入通過率。</p>
          )}
          <div className="ranking-list">
            {ranking.models.map((model, index) => (
              <div className={`ranking-row${model.ranked ? "" : " ranking-row-unranked"}`} key={model.model_id}>
                <span className="ranking-position" aria-label={model.ranked ? `第 ${index + 1} 名` : "未排名"}>
                  {model.ranked ? String(index + 1).padStart(2, "0") : "—"}
                </span>
                <div className="ranking-model">
                  {model.metric && <small>{model.metric}{!model.ranked && " · 尚未完整評分"}</small>}
                  <strong>{model.name}{model.provider === "demo" && <em>示範</em>}{model.dynamic_model && <em>動態路由</em>}{model.provisional && <em>執行中 · 暫不排名</em>}{model.cancelled_run && <em>已取消 · 暫不排名</em>}</strong>
                  <small>通過 {model.passed} / 已評分 {model.graded} · 已回答 {model.completed} / {model.total}{model.failed > 0 ? ` · 失敗 ${model.failed}` : ""}{model.cancelled > 0 ? ` · 已取消 ${model.cancelled}` : ""}</small>
                  {model.metric === "工具調用正確率" && Object.entries(model.categories || {}).map(([category, score]) => <small key={category}>{({ simple: "單一工具", multiple: "多工具選擇", parallel: "多個調用", parallel_multiple: "混合多工具", irrelevance: "不相關工具" } as Record<string, string>)[category]}：{score.passed} / {score.graded}（{(100 * score.passed / score.graded).toFixed(1)}%）</small>)}
                </div>
                <div className="ranking-measure">
                  <span className="ranking-value">{model.pass_rate === null ? "未評分" : `${model.pass_rate.toFixed(1)}%`}</span>
                  <div className="ranking-track" aria-hidden="true">
                    <div className="ranking-fill" style={{ width: `${model.pass_rate ?? 0}%` }} />
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="ranking-axis" aria-hidden="true"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>
          <p className="ranking-note">同一題庫版本的各次測試合併顯示，每個模型只採最近一次涵蓋整份題庫的測試；只計入有規則自動評分的回答，失敗題目另外列出。執行中或已取消的模型不列正式名次。{ranking.models.some((model) => model.dynamic_model) && " 動態路由成績可能由多個實際模型共同產生，逐題模型請至測試結果查看。"}{!ranking.is_final && " 測試完成前分數可能變動。"}</p>
          {ranking.models.some(model => model.metric === "工具調用正確率") && <p className="ranking-note">BFCL V3 Python 單輪子集：只合併相同工具調用模式與評分版本；全部題目可評分才列正式名次。此成績不代表完整官方排行榜。</p>}
          {ranking.models.some(model => model.metric && model.metric !== "工具調用正確率") && <p className="ranking-note">程式測試僅合併相同評分映像與執行時間上限；完整題組每題一次且全部可評分才標示 pass@1。這是本工具的隔離測試成績，不能直接視為官方排行榜分數。</p>}
          {error && <p className="ranking-note" role="alert">{error}</p>}
        </div>
      ) : null}
    </section>
  );
}
