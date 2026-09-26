import { useEffect, useState } from "react";
import { ArrowRight, BarChart3 } from "lucide-react";
import { api, type Ranking, type Run } from "../api";

export default function RankingChart({
  runs,
  onOpenRun,
  onNewRun,
}: {
  runs: Run[];
  onOpenRun: (id: string) => void;
  onNewRun: () => void;
}) {
  const choices = runs.filter(
    (run, index) =>
      !run.batch_id || runs.findIndex((candidate) => candidate.batch_id === run.batch_id) === index,
  );
  const [selectedId, setSelectedId] = useState("");
  const effectiveId = choices.some((run) => run.id === selectedId)
    ? selectedId
    : choices[0]?.id || "";
  const [ranking, setRanking] = useState<Ranking | null>(null);
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
    api<Ranking>(`/runs/${effectiveId}/ranking`, undefined, "GET", controller.signal)
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
      api<Ranking>(`/runs/${effectiveId}/ranking`, undefined, "GET", controller.signal)
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
          <p>同一次測試的規則通過率，按模型由高到低排列。</p>
        </div>
        {choices.length > 0 && (
          <label className="ranking-selector">
            <span>選擇測試</span>
            <select value={effectiveId} onChange={(event) => setSelectedId(event.target.value)}>
              {choices.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.batch_id ? run.name.replace(/ · \d+\/\d+$/, "") + "（整批）" : run.name}
                </option>
              ))}
            </select>
          </label>
        )}
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
          <div className="ranking-context">
            <div>
              <strong>{ranking.dataset_name}</strong>
              <span>{ranking.run_count > 1 ? `合併 ${ranking.run_count} 筆分批測試` : "單次測試"} · {ranking.status === "cancelled" ? "已取消，僅按已評分回答排名" : ranking.status === "completed_with_errors" ? "部分失敗，僅按已評分回答排名" : ranking.is_final ? "測試已完成" : "執行中，排名暫定"}</span>
            </div>
            <button className="text-button" onClick={() => onOpenRun(effectiveId)}>
              查看結果 <ArrowRight size={14} />
            </button>
          </div>
          {ranking.models.every((model) => model.graded === 0) && (
            <p className="ranking-note">這場測試尚無可自動評分的回答；人工評分與 API 失敗不計入通過率。</p>
          )}
          {ranking.models.length === 1 && (
            <p className="ranking-note">這場測試只有一個模型；同場加入更多模型即可比較名次。</p>
          )}
          <div className="ranking-list">
            {ranking.models.map((model, index) => (
              <div className="ranking-row" key={model.model_id}>
                <span className="ranking-position" aria-label={model.pass_rate === null ? "未排名" : `第 ${index + 1} 名`}>
                  {model.pass_rate === null ? "—" : String(index + 1).padStart(2, "0")}
                </span>
                <div className="ranking-model">
                  <strong>{model.name}{model.provider === "demo" && <em>示範</em>}{model.dynamic_model && <em>動態路由</em>}</strong>
                  <small>通過 {model.passed} / 已評分 {model.graded} · 已回答 {model.completed} / {model.total}{model.failed > 0 ? ` · 失敗 ${model.failed}` : ""}{model.cancelled > 0 ? ` · 已取消 ${model.cancelled}` : ""}</small>
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
          <p className="ranking-note">只計入有規則自動評分的回答；不同測試題庫不合併排名。{ranking.models.some((model) => model.dynamic_model) && " 動態路由成績可能由多個實際模型共同產生，逐題模型請至測試結果查看。"}{!ranking.is_final && " 測試完成前分數可能變動。"}</p>
          {error && <p className="ranking-note" role="alert">{error}</p>}
        </div>
      ) : null}
    </section>
  );
}
