function Wt() {
  var it, ct, dt, ut;
  const { React: e, antd: j, antdIcons: Y, getApiUrl: q, getApiToken: U } = window.QwenPaw.host, {
    Card: X,
    Table: L,
    Tag: $,
    Typography: Ce,
    Space: W,
    Button: T,
    Input: Q,
    Radio: Te,
    Collapse: Ut,
    Descriptions: se,
    Tooltip: Je,
    Spin: ye,
    message: Ue,
    theme: Ke
  } = j, { Text: G } = Ce, { TextArea: pt } = Q, { useState: C, useMemo: he, useCallback: z, useRef: Kt } = e, {
    InfoCircleOutlined: ze,
    DownOutlined: Ye,
    RightOutlined: gt,
    CheckCircleOutlined: Re,
    FieldTimeOutlined: Pe,
    FileTextOutlined: qe
  } = Y || {};
  function Xe(t) {
    var i, d;
    const n = (d = (i = t == null ? void 0 : t.content) == null ? void 0 : i[0]) == null ? void 0 : d.data, o = n == null ? void 0 : n.arguments;
    if (typeof o == "string")
      try {
        return JSON.parse(o);
      } catch {
        return {};
      }
    return o ?? {};
  }
  function yt() {
    return window.currentSessionId ?? null;
  }
  function ae(t) {
    return typeof t == "string" ? t : t && typeof t == "object" && "text" in t ? t.text : String(t ?? "");
  }
  function ht(t) {
    if (t == null) return !0;
    const n = ae(t).trim();
    return !!(!n || /^[¥$]?0+(\.0+)?$/.test(n) || /^[-–—]+$/.test(n));
  }
  async function Et(t, n) {
    try {
      const o = U(), i = {
        "Content-Type": "application/json"
      };
      return o && (i.Authorization = `Bearer ${o}`), (await fetch(q("/interaction"), {
        method: "POST",
        headers: i,
        body: JSON.stringify({ session_id: t, result: n })
      })).ok;
    } catch {
      return !1;
    }
  }
  function Ge(t) {
    if (!t) return null;
    if (typeof t == "string")
      try {
        const n = JSON.parse(t);
        if (Array.isArray(n)) {
          const o = n.find(
            (i) => (i == null ? void 0 : i.type) === "text" && (i == null ? void 0 : i.text)
          );
          return (o == null ? void 0 : o.text) ?? null;
        }
        if (typeof n == "string") return n;
      } catch {
        return t;
      }
    if (Array.isArray(t)) {
      const n = t.find((o) => (o == null ? void 0 : o.type) === "text" && (o == null ? void 0 : o.text));
      return (n == null ? void 0 : n.text) ?? null;
    }
    return null;
  }
  function xt(t) {
    var l, c;
    if (!t || t.length < 2) return null;
    const n = (c = (l = t[1]) == null ? void 0 : l.data) == null ? void 0 : c.output, o = Ge(n);
    if (!o) return null;
    if (o.startsWith("Error:")) return o;
    const i = o.match(/^用户选择了「(.+?)」并确认部署$/);
    if (i) return `已确认部署「${i[1]}」`;
    const d = o.match(
      /^用户选择「(.+?)」并要求调整[：:](.+)$/
    );
    if (d)
      return `已选择「${d[1]}」并调整：${d[2]}`;
    if (o === "用户确认部署") return "已确认部署";
    const g = o.match(/^用户要求调整资源[：:](.+)$/);
    return g ? `已反馈调整意见：${g[1]}` : "已确认";
  }
  const Ve = [
    "资源类型",
    "资源用途",
    "规格",
    "地域",
    "数量",
    "计费方式",
    "时长",
    "原价",
    "优惠",
    "预估算费用"
  ], wt = new Set(
    Ve.map((t) => t.toLowerCase())
  );
  function Le(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = ae(t[0]).trim().toLowerCase();
    return wt.has(n);
  }
  function Qe(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = ae(t[0]).trim();
    return /^(合计|总计|total)/i.test(n);
  }
  function St(t) {
    const n = [];
    let o = [];
    for (const i of t)
      o.push(i), Qe(i) && (n.push(o), o = []);
    return o.length > 0 && (n.length > 0 ? n[n.length - 1].push(...o) : n.push(o)), n.length > 0 ? n : [t];
  }
  function At(t) {
    return typeof t == "string" ? t : t && typeof t == "object" && t.text ? t.url ? e.createElement(
      "a",
      {
        href: t.url,
        target: "_blank",
        rel: "noopener noreferrer"
      },
      t.text
    ) : t.text : String(t ?? "");
  }
  function bt({ data: t }) {
    var pe, m, b;
    const [n, o] = C("confirm"), [i, d] = C(""), [g, l] = C(!1), [c, s] = C(null), [I, A] = C(
      {}
    ), _ = e.useRef(!1), F = e.useRef(null), [, ne] = C(0), M = t == null ? void 0 : t.content, B = M && M.length >= 2 && ((m = (pe = M[1]) == null ? void 0 : pe.data) == null ? void 0 : m.output), H = he(
      () => xt(M),
      [M]
    ), R = _.current || B || H !== null, u = he(() => {
      const E = Xe(t), a = E == null ? void 0 : E.data;
      if (!a) return null;
      try {
        const y = typeof a == "string" ? JSON.parse(a) : a;
        let p;
        if (E.strategy_names)
          try {
            const O = typeof E.strategy_names == "string" ? JSON.parse(E.strategy_names) : E.strategy_names;
            p = Array.isArray(O) ? O : [];
          } catch {
            p = [];
          }
        else y != null && y.proposal_names ? p = y.proposal_names : p = [];
        const S = p.length >= 2 ? p.length : 0;
        let k;
        if (Array.isArray(y) && y.length > 0)
          if (Array.isArray(y[0]) && y[0].length === 10 && !Array.isArray(y[0][0])) {
            const D = y.filter(
              (le) => !Le(le)
            );
            if (D.filter(
              (le) => Qe(le)
            ).length >= 2)
              k = St(D);
            else if (S >= 2 && D.length >= S * 2) {
              const le = Math.ceil(D.length / S);
              k = [];
              for (let ge = 0; ge < D.length; ge += le)
                k.push(D.slice(ge, ge + le));
            } else
              k = [D];
          } else
            k = y.map(
              (D) => D.filter(
                (ee) => Array.isArray(ee) && ee.length === 10 && !Le(ee)
              )
            );
        else if (y != null && y.proposals)
          k = y.proposals.map(
            (O) => O.filter((D) => !Le(D))
          );
        else
          return null;
        if (k = k.filter((O) => O.length > 0), k.length === 0) return null;
        const ce = ["方案一", "方案二", "方案三", "方案四", "方案五"];
        if (p.length < k.length)
          for (let O = p.length; O < k.length; O++)
            p.push(ce[O] || `方案${O + 1}`);
        return { proposals: k, names: p };
      } catch {
        return null;
      }
    }, [t]), x = yt(), f = (((b = u == null ? void 0 : u.proposals) == null ? void 0 : b.length) ?? 0) > 1, P = z(async () => {
      if (!x || R || !u) return;
      const E = f ? c : 0, a = u.names[E ?? 0] || `方案${(E ?? 0) + 1}`;
      let y;
      n === "confirm" ? y = `用户选择了「${a}」并确认部署` : y = `用户选择「${a}」并要求调整：${i.trim() || "未填写具体要求"}`, l(!0);
      const p = await Et(x, y);
      l(!1), p ? (_.current = !0, n === "confirm" ? F.current = `已确认部署「${a}」` : F.current = `已选择「${a}」并调整：${i.trim()}`, ne((S) => S + 1), Ue.success(
        n === "confirm" ? "已确认部署方案" : "已提交调整意见"
      )) : Ue.error("操作失败，请重试");
    }, [
      x,
      R,
      u,
      n,
      i,
      c,
      f
    ]), Se = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created";
    if (!u)
      return Se ? e.createElement(
        "div",
        {
          style: {
            width: "100%",
            borderRadius: 10,
            border: "1px solid #f0f0f0",
            background: "#fff",
            padding: "24px 16px",
            margin: "4px 0",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12
          }
        },
        e.createElement(ye, { size: "default" }),
        e.createElement(
          G,
          { type: "secondary", style: { fontSize: 13 } },
          "正在生成资源方案..."
        )
      ) : e.createElement(
        X,
        { size: "small", style: { margin: "4px 0" } },
        e.createElement(G, { type: "secondary" }, "无法解析方案数据")
      );
    const { proposals: Z, names: ue } = u, J = Ve.map((E, a) => ({
      title: E,
      dataIndex: `col_${a}`,
      key: `col_${a}`,
      render: (y) => At(y),
      ellipsis: a < 3
    }));
    let fe = "待确认", V = "processing";
    R && (V = "success", fe = F.current || H || "已确认");
    const re = e.createElement(
      $,
      {
        color: V,
        style: { marginLeft: 4 }
      },
      fe
    ), Ae = e.createElement(
      W,
      { size: 8 },
      e.createElement("span", null, "☁️"),
      e.createElement(
        G,
        { strong: !0, style: { fontSize: 14 } },
        R ? "资源配置方案" : "请确认您的资源配置方案"
      ),
      re
    ), me = Z.map((E, a) => {
      const y = f ? c === a : !0, p = I[a] || !1, S = (v) => {
        const te = ae(v[0] || "").trim();
        return /^合计|^总计|^total/i.test(te);
      }, k = E.find(S), ce = E.filter((v) => !S(v)), O = ce.map((v) => ({
        type: ae(v[0] || ""),
        purpose: ae(v[1] || ""),
        spec: ae(v[2] || ""),
        cost: v[9] ?? null
      })), D = k ? ae(k[9] ?? "") : "", ee = E.map((v, te) => {
        const De = { key: te };
        return v.forEach((Ie, je) => {
          De[`col_${je}`] = Ie;
        }), De;
      }), le = y ? "2px solid #1677ff" : "1px solid #e8e8e8", ge = y ? "0 0 0 2px #e6f4ff" : "none";
      return e.createElement(
        "div",
        {
          key: a,
          style: {
            flex: 1,
            minWidth: 240,
            border: le,
            borderRadius: 8,
            cursor: f ? "pointer" : "default",
            transition: "all 0.2s ease",
            boxShadow: ge,
            background: "#fff"
          },
          onClick: f ? () => s(a) : void 0
        },
        e.createElement(
          "div",
          { style: { padding: "10px 12px" } },
          // Proposal name
          e.createElement(
            G,
            {
              strong: !0,
              style: { fontSize: 14, display: "block", marginBottom: 8 }
            },
            ue[a]
          ),
          ...O.map(
            (v, te) => e.createElement(
              "div",
              {
                key: te,
                style: {
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "4px 0",
                  borderBottom: te < O.length - 1 ? "1px solid #f5f5f5" : "none"
                }
              },
              e.createElement(
                "div",
                { style: { flex: 1, minWidth: 0 } },
                e.createElement(
                  "span",
                  { style: { fontSize: 12, color: "#262626" } },
                  v.type
                ),
                v.spec && e.createElement(
                  "span",
                  {
                    style: { fontSize: 11, color: "#8c8c8c", marginLeft: 6 }
                  },
                  v.spec
                )
              ),
              !ht(v.cost) && e.createElement(
                "span",
                {
                  style: {
                    fontSize: 12,
                    color: "#595959",
                    flexShrink: 0,
                    marginLeft: 8
                  }
                },
                ae(v.cost)
              )
            )
          ),
          // Total cost
          D && e.createElement(
            "div",
            {
              style: {
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginTop: 6,
                paddingTop: 6,
                borderTop: "1px dashed #e8e8e8"
              }
            },
            e.createElement(
              "span",
              { style: { fontSize: 12, fontWeight: 500 } },
              "合计"
            ),
            e.createElement(
              "span",
              {
                style: { fontSize: 14, fontWeight: 700, color: "#fa541c" }
              },
              D
            )
          ),
          // Details toggle
          e.createElement(
            "div",
            {
              style: {
                display: "flex",
                alignItems: "center",
                gap: 4,
                color: "#8c8c8c",
                fontSize: 12,
                cursor: "pointer",
                marginTop: 6
              },
              onClick: (v) => {
                v.stopPropagation(), A((te) => ({
                  ...te,
                  [a]: !te[a]
                }));
              }
            },
            e.createElement(
              p && Ye ? Ye : gt || "span",
              {
                style: { fontSize: 10 }
              }
            ),
            e.createElement(
              "span",
              null,
              `明细 · ${ce.length} 项`
            )
          ),
          p && e.createElement(
            "div",
            {
              onClick: (v) => v.stopPropagation(),
              style: { marginTop: 4, maxHeight: 260, overflow: "auto" }
            },
            e.createElement(L, {
              columns: J,
              dataSource: ee,
              pagination: !1,
              size: "small",
              scroll: { x: "max-content" }
            })
          )
        )
      );
    }), oe = e.createElement(
      "div",
      {
        style: {
          background: "#fffbe6",
          border: "1px solid #ffe58f",
          borderRadius: 6,
          padding: "8px 12px",
          marginBottom: 10,
          display: "flex",
          alignItems: "flex-start",
          gap: 8
        }
      },
      ze ? e.createElement(ze, {
        style: {
          color: "#faad14",
          fontSize: 14,
          flexShrink: 0,
          marginTop: 1
        }
      }) : e.createElement("span", null, "⚠️"),
      e.createElement(
        "span",
        {
          style: { fontSize: 12, color: "#8c6e00", lineHeight: 1.5 }
        },
        "在服务部署与配置过程中，可能因实际资源需求变化导致资源变配及费用调整，请及时关注实际资源使用情况与账单详情。"
      )
    ), Ee = !R && x && !(f && c === null) && e.createElement(
      "div",
      null,
      e.createElement(
        "div",
        {
          style: {
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            marginBottom: 8
          }
        },
        // Confirm option
        e.createElement(
          "div",
          {
            style: {
              flex: 1,
              minWidth: 140,
              border: `1px solid ${n === "confirm" ? "#1677ff" : "#e8e8e8"}`,
              borderRadius: 6,
              padding: "8px 12px",
              cursor: "pointer",
              transition: "all 0.15s ease",
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: n === "confirm" ? "#e6f4ff" : "transparent"
            },
            onClick: () => o("confirm")
          },
          e.createElement(Te, { checked: n === "confirm" }),
          e.createElement(
            "span",
            { style: { fontSize: 13 } },
            "确认部署"
          )
        ),
        // Adjust option
        e.createElement(
          "div",
          {
            style: {
              flex: 1,
              minWidth: 140,
              border: `1px solid ${n === "adjust" ? "#1677ff" : "#e8e8e8"}`,
              borderRadius: 6,
              padding: "8px 12px",
              transition: "all 0.15s ease",
              background: n === "adjust" ? "#e6f4ff" : "transparent"
            }
          },
          e.createElement(
            "div",
            {
              style: {
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: "pointer"
              },
              onClick: () => o("adjust")
            },
            e.createElement(Te, { checked: n === "adjust" }),
            e.createElement(
              "span",
              { style: { fontSize: 13 } },
              "调整资源"
            )
          ),
          n === "adjust" && e.createElement(pt, {
            value: i,
            onChange: (E) => d(E.target.value),
            placeholder: "请输入调整要求",
            autoSize: { minRows: 1, maxRows: 3 },
            style: { fontSize: 12, marginTop: 6 }
          })
        )
      ),
      // Footer
      e.createElement(
        "div",
        {
          style: {
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            paddingTop: 8
          }
        },
        e.createElement(
          G,
          { type: "secondary", style: { fontSize: 11 } },
          f ? "一小时后未操作将自动选择第一个方案" : "一小时后未操作将自动确认部署"
        ),
        e.createElement(
          T,
          {
            type: "primary",
            size: "small",
            loading: g,
            onClick: P,
            disabled: n === "adjust" && !i.trim()
          },
          n === "confirm" ? "确认部署" : "提交调整"
        )
      )
    ), N = f && c === null && !R && e.createElement(
      "div",
      {
        style: {
          textAlign: "center",
          padding: "8px 0 4px",
          color: "rgba(0,0,0,0.45)",
          fontSize: 12
        }
      },
      "请点击选择一个方案后继续操作"
    );
    return e.createElement(
      "div",
      {
        style: {
          width: "100%",
          borderRadius: 10,
          border: "1px solid #f0f0f0",
          overflow: "hidden",
          background: "#fff",
          padding: "12px 16px",
          margin: "4px 0"
        }
      },
      // Header
      e.createElement("div", { style: { marginBottom: 10 } }, Ae),
      // Proposals grid
      e.createElement(
        "div",
        {
          style: {
            display: "flex",
            gap: 10,
            marginBottom: 12,
            flexWrap: "wrap"
          }
        },
        ...me
      ),
      N,
      oe,
      !R && Ee
    );
  }
  function kt({ data: t }) {
    const [n, o] = C(null), [i, d] = C(!1), g = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created", l = he(() => {
      const u = Xe(t);
      return (u == null ? void 0 : u.loop_dir) || null;
    }, [t]), c = he(() => {
      var x, f, P;
      const u = Ge((P = (f = (x = t == null ? void 0 : t.content) == null ? void 0 : x[1]) == null ? void 0 : f.data) == null ? void 0 : P.output);
      if (!u) return null;
      try {
        return JSON.parse(u);
      } catch {
        return null;
      }
    }, [t]), s = (c == null ? void 0 : c.status) === "ok", I = (c == null ? void 0 : c.status) === "error", A = I ? (c == null ? void 0 : c.message) || "未知错误" : null, _ = z(async () => {
      if (l)
        try {
          const u = U(), x = {};
          u && (x.Authorization = `Bearer ${u}`);
          const f = await fetch(
            q(`/prd?loop_dir=${encodeURIComponent(l)}`),
            { headers: x }
          );
          if (!f.ok) {
            d(!0);
            return;
          }
          const P = await f.json();
          P && Array.isArray(P.userStories) ? (o(P), d(!1)) : d(!0);
        } catch {
          d(!0);
        }
    }, [l]);
    if (e.useEffect(() => {
      !g && s && l && _();
    }, [g, s, l, _]), g)
      return e.createElement(
        "div",
        {
          style: {
            width: "100%",
            borderRadius: 10,
            border: "1px solid #f0f0f0",
            background: "#fff",
            padding: "24px 16px",
            margin: "4px 0",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12
          }
        },
        e.createElement(ye, { size: "default" }),
        e.createElement(
          G,
          { type: "secondary", style: { fontSize: 13 } },
          "正在更新 PRD..."
        )
      );
    if (I)
      return e.createElement(
        "div",
        {
          style: {
            width: "100%",
            borderRadius: 10,
            border: "1px solid #fff1f0",
            background: "#fff1f0",
            padding: "12px 16px",
            margin: "4px 0",
            display: "flex",
            alignItems: "center",
            gap: 8
          }
        },
        e.createElement(
          G,
          { type: "danger", style: { fontSize: 13 } },
          `PRD 格式错误，将会修正：${A}`
        )
      );
    if (!s || i || !n) return null;
    const F = n.userStories, ne = [...F].sort(
      (u, x) => (u.priority || 99) - (x.priority || 99)
    ), M = F.filter((u) => u.passes).length, B = [
      {
        title: "状态",
        key: "status",
        width: 50,
        align: "center",
        render: (u, x) => {
          if (x.passes) {
            const P = Re ? e.createElement(Re, {
              style: { color: "#52c41a", fontSize: 18 }
            }) : "✅";
            return e.createElement(Je, { title: "已完成" }, P);
          }
          const f = Pe ? e.createElement(Pe, {
            style: { color: "#faad14", fontSize: 18 }
          }) : "🕐";
          return e.createElement(Je, { title: "待处理" }, f);
        }
      },
      {
        title: "ID",
        dataIndex: "id",
        key: "id",
        width: 85,
        render: (u) => e.createElement($, { color: "blue" }, u)
      },
      {
        title: "标题",
        dataIndex: "title",
        key: "title",
        render: (u) => e.createElement(G, { strong: !0 }, u)
      },
      {
        title: "优先级",
        key: "priority",
        width: 70,
        render: (u, x) => {
          const f = x.priority;
          return e.createElement(
            $,
            { color: "default" },
            f != null ? String(f) : "-"
          );
        }
      },
      {
        title: "描述",
        dataIndex: "description",
        key: "description",
        ellipsis: !0
      },
      {
        title: "验收标准",
        key: "acceptance",
        width: 200,
        render: (u, x) => {
          const f = x.acceptanceCriteria;
          return typeof f == "string" ? e.createElement(
            "div",
            {
              style: { fontSize: 12, color: "#666", whiteSpace: "pre-wrap" }
            },
            f.length > 100 ? f.slice(0, 100) + "..." : f
          ) : Array.isArray(f) ? e.createElement(
            "div",
            { style: { fontSize: 12, color: "#666" } },
            f.length > 2 ? f.slice(0, 2).join(", ") + "..." : f.join(", ")
          ) : "-";
        }
      }
    ], H = e.createElement(
      W,
      { size: 8 },
      qe ? e.createElement(qe, { style: { color: "#1677ff" } }) : null,
      e.createElement(
        "span",
        { style: { fontSize: 14 } },
        e.createElement(G, { strong: !0 }, n.project || "PRD")
      )
    ), R = e.createElement(L, {
      columns: B,
      dataSource: ne.map((u) => ({ ...u, key: u.id })),
      size: "small",
      pagination: !1,
      scroll: { x: "max-content" },
      style: { marginBottom: 4 }
    });
    return e.createElement(
      "div",
      {
        style: {
          width: "100%",
          borderRadius: 10,
          border: "1px solid #f0f0f0",
          overflow: "hidden",
          background: "#fff",
          padding: "12px 16px",
          margin: "4px 0"
        }
      },
      e.createElement("div", { style: { marginBottom: 8 } }, H),
      e.createElement(se, {
        size: "small",
        column: { xs: 1, sm: 2, md: 3 },
        style: { marginBottom: 12 },
        bordered: !1,
        items: [
          {
            key: "progress",
            label: "进度",
            children: `${M}/${F.length} 完成`
          }
        ]
      }),
      R,
      e.createElement(
        "div",
        {
          style: {
            fontSize: 11,
            color: "#8c8c8c",
            display: "flex",
            alignItems: "center",
            gap: 8
          }
        },
        Re ? e.createElement(Re, {
          style: { color: "#52c41a", fontSize: 14 }
        }) : "✅",
        e.createElement("span", null, "已完成"),
        e.createElement("span", { style: { margin: "0 4px" } }, "·"),
        Pe ? e.createElement(Pe, {
          style: { color: "#faad14", fontSize: 14 }
        }) : "🕐",
        e.createElement("span", null, "待处理")
      )
    );
  }
  const {
    Form: ie,
    Select: Oe,
    Drawer: Ct,
    Modal: Ze,
    Empty: Tt,
    Badge: et,
    Divider: vt,
    message: K
  } = j, {
    ApiOutlined: tt,
    PlusOutlined: nt,
    ReloadOutlined: $e,
    DeleteOutlined: rt,
    LinkOutlined: ot,
    DisconnectOutlined: Yt
  } = Y || {}, { useEffect: lt } = e, xe = "/a2a/agents";
  function Ne() {
    var t;
    try {
      const n = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage");
      if (n) {
        const o = JSON.parse(n);
        return ((t = o == null ? void 0 : o.state) == null ? void 0 : t.selectedAgent) || null;
      }
    } catch {
    }
    return null;
  }
  async function we(t, n) {
    const o = q(t), i = U == null ? void 0 : U(), d = Ne(), g = {
      "Content-Type": "application/json",
      ...i ? { Authorization: `Bearer ${i}` } : {},
      ...d ? { "X-Agent-Id": d } : {}
    }, l = await fetch(o, {
      ...n,
      headers: { ...g, ...(n == null ? void 0 : n.headers) || {} }
    });
    if (!l.ok) {
      const c = await l.text().catch(() => "");
      throw new Error(c || `HTTP ${l.status}`);
    }
    return l.status === 204 || l.headers.get("content-length") === "0" ? null : l.json();
  }
  function It(t) {
    var c;
    const { agent: n, onClick: o } = t, i = n.status === "connected", d = i ? "#52c41a" : n.status === "error" ? "#ff4d4f" : "#d9d9d9", g = i ? "已连接" : n.status === "error" ? "错误" : "未连接", l = {
      gateway: "阿里云Agent Hub",
      bearer: "Bearer Token",
      api_key: "API Key"
    };
    return e.createElement(
      X,
      {
        hoverable: !0,
        onClick: o,
        size: "small",
        style: { cursor: "pointer" },
        title: e.createElement(
          W,
          null,
          e.createElement(et, { color: d }),
          e.createElement(
            "span",
            null,
            n.alias || n.name || n.url
          )
        ),
        extra: n.auth_type ? e.createElement(
          $,
          { color: "blue" },
          l[n.auth_type] || n.auth_type
        ) : null
      },
      e.createElement(
        "div",
        { style: { fontSize: 12, color: "#666" } },
        e.createElement(
          "div",
          { style: { marginBottom: 4 } },
          ot ? e.createElement(ot, { style: { marginRight: 4 } }) : null,
          n.url
        ),
        n.description ? e.createElement(
          "div",
          { style: { marginBottom: 4, color: "#999" } },
          n.description
        ) : null,
        ((c = n.skills) == null ? void 0 : c.length) > 0 ? e.createElement(
          "div",
          null,
          n.skills.slice(0, 3).map(
            (s, I) => e.createElement(
              $,
              { key: I, style: { fontSize: 11 } },
              s.name
            )
          ),
          n.skills.length > 3 ? e.createElement(
            $,
            { style: { fontSize: 11 } },
            `+${n.skills.length - 3}`
          ) : null
        ) : null,
        e.createElement(
          "div",
          { style: { marginTop: 4, color: d, fontSize: 11 } },
          g,
          n.error ? ` - ${n.error}` : ""
        )
      )
    );
  }
  function _t() {
    const t = e.useRef(Ne()), [n, o] = C(t.current);
    return lt(() => {
      const i = () => {
        const g = Ne();
        g !== t.current && (t.current = g, o(g));
      }, d = setInterval(i, 200);
      return window.addEventListener("storage", i), () => {
        clearInterval(d), window.removeEventListener("storage", i);
      };
    }, []), n;
  }
  function zt() {
    var ft, mt;
    const { token: t } = Ke.useToken(), n = _t(), [o, i] = C([]), [d, g] = C(!0), [l, c] = C(!1), [s, I] = C(null), [A, _] = C(!1), [F, ne] = C(!1), [M, B] = C(!1), [H, R] = C(!1), [u, x] = C(""), [f] = ie.useForm(), [P, Se] = C(!1), [Z, ue] = C(!1), [J, fe] = C([]), [V, re] = C(
      /* @__PURE__ */ new Set()
    ), [Ae, me] = C(
      []
    ), oe = e.useRef(null), Ee = (r) => !r || !r.trim() ? null : /\s/.test(r) ? "别名不能包含空格" : null, N = he(
      () => new Set(o.map((r) => r.url)),
      [o]
    ), pe = e.useRef(N);
    pe.current = N;
    const m = z(async () => {
      g(!0);
      try {
        const r = await we(xe);
        i((r == null ? void 0 : r.agents) || []);
      } catch {
        i([]);
      } finally {
        g(!1);
      }
    }, []);
    lt(() => {
      m();
    }, [n]);
    const b = z(() => {
      _(!0), I(null), c(!0), f.resetFields(), f.setFieldsValue({
        url: "",
        alias: "",
        auth_type: "",
        auth_token: ""
      });
    }, [f]), E = z((r) => {
      _(!1), I(r), c(!0);
    }, []), a = z(() => {
      R(!1), x("");
    }, []), y = z(async () => {
      if (!s || !u.trim()) return;
      const r = Ee(u);
      if (r) {
        K.error(r);
        return;
      }
      const h = s.alias || s.url, w = u.trim();
      if (w === h) {
        a();
        return;
      }
      try {
        const de = await we(
          `${xe}?alias=${encodeURIComponent(h)}`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ new_alias: w })
          }
        );
        K.success("别名已修改"), R(!1), I(de), await m();
      } catch (de) {
        K.error(de.message || "修改失败");
      }
    }, [s, u, m, a]), p = z(() => {
      a(), c(!1), I(null), _(!1), f.resetFields();
    }, [a, f]), S = z(async () => {
      let r;
      try {
        r = await f.validateFields();
      } catch {
        return;
      }
      const h = {
        url: String(r.url || "").trim(),
        alias: String(r.alias || "").trim() || void 0,
        auth_type: String(r.auth_type || ""),
        auth_token: String(r.auth_token || "")
      };
      if (h.url) {
        ne(!0);
        try {
          await we(xe, {
            method: "POST",
            body: JSON.stringify(h)
          }), K.success("A2A Agent 注册成功"), await m(), p();
        } catch (w) {
          K.error(w.message || "注册失败");
        } finally {
          ne(!1);
        }
      }
    }, [f, m, p]), k = z(async () => {
      if (!s) return;
      const r = s.alias || s.url, h = s.name || r;
      Ze.confirm({
        title: "确认删除",
        content: `确定删除 A2A Agent「${h}」吗？此操作不可撤销。`,
        okText: "删除",
        cancelText: "取消",
        okButtonProps: { danger: !0 },
        async onOk() {
          try {
            await we(`${xe}?alias=${encodeURIComponent(r)}`, {
              method: "DELETE"
            }), K.success(`已删除 A2A Agent「${h}」`), await m(), p();
          } catch (w) {
            K.error(w.message || "删除失败");
          }
        }
      });
    }, [s, m, p]), ce = z(async () => {
      if (!s) return;
      const r = s.alias || s.url;
      B(!0);
      try {
        const h = await we(
          `${xe}/refresh?alias=${encodeURIComponent(r)}`,
          {
            method: "POST"
          }
        );
        K.success("Agent Card 已刷新"), await m(), h && I(h);
      } catch (h) {
        K.error(h.message || "刷新失败");
      } finally {
        B(!1);
      }
    }, [s, m]), O = z(() => {
      s && (x(s.alias || ""), R(!0));
    }, [s]), D = z(() => {
      Se(!0), fe([]), re(/* @__PURE__ */ new Set()), me([]), oe.current = null, le();
    }, []), ee = z(() => {
      Z && oe.current && oe.current.abort(), Se(!1), fe([]), re(/* @__PURE__ */ new Set()), me([]), oe.current = null;
    }, [Z]), le = z(async () => {
      ue(!0);
      const r = new AbortController();
      oe.current = r;
      try {
        const h = U == null ? void 0 : U(), w = Ne(), de = {
          ...h ? { Authorization: `Bearer ${h}` } : {},
          ...w ? { "X-Agent-Id": w } : {}
        }, ke = await fetch(q("/a2a/import"), {
          method: "GET",
          headers: de,
          signal: r.signal
        });
        if (!ke.ok) {
          const _e = await ke.text().catch(() => "");
          throw new Error(_e || `HTTP ${ke.status}`);
        }
        const We = await ke.json(), Fe = (We == null ? void 0 : We.agents) || [];
        if (Fe.length === 0) {
          K.warning("未找到可用的 Agent");
          return;
        }
        fe(Fe);
        const jt = pe.current;
        re(
          new Set(
            Fe.filter((_e) => !jt.has(_e.url)).map((_e) => _e.url)
          )
        );
      } catch (h) {
        if ((h == null ? void 0 : h.name) === "AbortError") return;
        K.error(h.message || "获取 Agent 列表失败");
      } finally {
        ue(!1), oe.current = null;
      }
    }, []), ge = z((r) => {
      re((h) => {
        const w = new Set(h);
        return w.has(r) ? w.delete(r) : w.add(r), w;
      });
    }, []), v = z(() => {
      re(
        new Set(
          J.filter((r) => !N.has(r.url)).map((r) => r.url)
        )
      );
    }, [J, N]), te = z(() => {
      re(/* @__PURE__ */ new Set());
    }, []), De = z(async () => {
      const r = J.filter(
        (w) => V.has(w.url) && !N.has(w.url)
      );
      if (r.length === 0) {
        K.warning("请至少选择一个 Agent");
        return;
      }
      ue(!0), me([]);
      const h = [];
      for (const w of r) {
        try {
          await we(xe, {
            method: "POST",
            body: JSON.stringify({
              url: w.url,
              alias: w.name || void 0,
              auth_type: w.auth_type || "gateway",
              auth_token: ""
            })
          }), h.push({ name: w.name || w.url, success: !0 });
        } catch (de) {
          h.push({
            name: w.name || w.url,
            success: !1,
            error: de.message || "注册失败"
          });
        }
        me([...h]);
      }
      await m(), K.success(
        `导入完成：成功 ${h.filter((w) => w.success).length} 个，失败 ${h.filter((w) => !w.success).length} 个`
      ), ue(!1), setTimeout(() => ee(), 800);
    }, [J, V, m, N]), Ie = ((ft = ie.useWatch) == null ? void 0 : ft.call(ie, "auth_type", f)) ?? "", je = e.createElement(
      ie,
      { form: f, layout: "vertical" },
      e.createElement(
        ie.Item,
        {
          name: "url",
          label: "Agent URL",
          rules: [{ required: !0, message: "请输入 Agent URL" }]
        },
        e.createElement(Q, {
          placeholder: "https://agent.example.com"
        })
      ),
      e.createElement(
        ie.Item,
        {
          name: "alias",
          label: "别名",
          rules: [
            {
              validator: (r, h) => {
                const w = Ee(h);
                return w ? Promise.reject(new Error(w)) : Promise.resolve();
              }
            }
          ]
        },
        e.createElement(Q, {
          placeholder: "输入别名（可选，仅小写字母、数字和连字符）"
        })
      ),
      e.createElement(
        ie.Item,
        { name: "auth_type", label: "认证类型" },
        e.createElement(
          Oe,
          { allowClear: !0, placeholder: "无认证" },
          e.createElement(
            Oe.Option,
            { value: "bearer" },
            "Bearer Token"
          ),
          e.createElement(Oe.Option, { value: "api_key" }, "API Key"),
          e.createElement(
            Oe.Option,
            { value: "gateway" },
            "阿里云Agent Hub"
          )
        )
      ),
      Ie === "gateway" ? e.createElement(
        "div",
        {
          style: {
            marginBottom: 16,
            padding: "8px 12px",
            background: "#f6ffed",
            border: "1px solid #b7eb8f",
            borderRadius: 6,
            fontSize: 12,
            color: "#52c41a"
          }
        },
        "阿里云Agent Hub 模式将自动使用环境变量中的 AK-SK 换取 Bearer Token"
      ) : null,
      Ie && Ie !== "gateway" ? e.createElement(
        ie.Item,
        { name: "auth_token", label: "认证凭证" },
        e.createElement(Q.Password, {
          placeholder: "Bearer Token 或 API Key"
        })
      ) : null
    ), Dt = s ? e.createElement(
      "div",
      null,
      e.createElement(
        se,
        { column: 1, bordered: !0, size: "small" },
        e.createElement(
          se.Item,
          { label: "URL" },
          s.url
        ),
        e.createElement(
          se.Item,
          { label: "别名" },
          H ? e.createElement(
            "div",
            {
              style: { display: "flex", alignItems: "center", gap: 6 }
            },
            e.createElement(Q, {
              value: u,
              onChange: (r) => x(r.target.value),
              onPressEnter: y,
              autoFocus: !0,
              placeholder: "输入新别名",
              size: "small",
              style: { flex: 1 }
            }),
            e.createElement(
              T,
              {
                type: "link",
                size: "small",
                onClick: y,
                disabled: !u.trim(),
                style: { padding: 0 }
              },
              "保存"
            )
          ) : e.createElement(
            "div",
            {
              style: { display: "flex", alignItems: "center", gap: 8 }
            },
            e.createElement("span", null, s.alias || "-"),
            e.createElement(
              "a",
              {
                style: { fontSize: 12 },
                onClick: O
              },
              "修改"
            )
          )
        ),
        e.createElement(
          se.Item,
          { label: "Agent 名称" },
          s.name || "-"
        ),
        e.createElement(
          se.Item,
          { label: "状态" },
          e.createElement(et, {
            color: s.status === "connected" ? "#52c41a" : s.status === "error" ? "#ff4d4f" : "#d9d9d9",
            text: s.status === "connected" ? "已连接" : s.status === "error" ? "错误" : "未连接"
          })
        ),
        e.createElement(
          se.Item,
          { label: "认证类型" },
          s.auth_type ? e.createElement(
            $,
            { color: "blue" },
            {
              gateway: "阿里云Agent Hub",
              bearer: "Bearer Token",
              api_key: "API Key"
            }[s.auth_type] || s.auth_type
          ) : "无认证"
        ),
        e.createElement(
          se.Item,
          { label: "描述" },
          s.description || "-"
        ),
        e.createElement(
          se.Item,
          { label: "版本" },
          s.version || "-"
        )
      ),
      ((mt = s.skills) == null ? void 0 : mt.length) > 0 ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "技能"),
        ...s.skills.map(
          (r, h) => e.createElement(
            X,
            { key: h, size: "small", style: { marginBottom: 8 } },
            e.createElement("strong", null, r.name),
            r.description ? e.createElement(
              "div",
              { style: { color: "#666", fontSize: 12 } },
              r.description
            ) : null
          )
        )
      ) : null,
      s.capabilities ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "能力"),
        e.createElement(
          W,
          null,
          e.createElement(
            $,
            {
              color: s.capabilities.streaming ? "green" : "default"
            },
            "Streaming"
          ),
          e.createElement(
            $,
            {
              color: s.capabilities.push_notifications ? "green" : "default"
            },
            "Push Notifications"
          )
        )
      ) : null,
      s.error ? e.createElement(
        "div",
        {
          style: {
            marginTop: 16,
            padding: "8px 12px",
            background: "#fff2f0",
            border: "1px solid #ffccc7",
            borderRadius: 6,
            fontSize: 12,
            color: "#ff4d4f"
          }
        },
        s.error
      ) : null,
      e.createElement(vt, null),
      e.createElement(
        W,
        null,
        e.createElement(
          T,
          {
            type: "primary",
            icon: $e ? e.createElement($e) : null,
            loading: M,
            onClick: ce
          },
          "刷新 Agent Card"
        ),
        e.createElement(
          T,
          {
            danger: !0,
            icon: rt ? e.createElement(rt) : null,
            onClick: k
          },
          "删除"
        )
      )
    ) : null, Lt = e.createElement(
      Ct,
      {
        title: A ? "注册远程 A2A Agent" : (s == null ? void 0 : s.name) || (s == null ? void 0 : s.alias) || "Agent 详情",
        open: l,
        onClose: p,
        width: 480,
        footer: A ? e.createElement(
          W,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(T, { onClick: p }, "取消"),
          e.createElement(
            T,
            { type: "primary", loading: F, onClick: S },
            "注册"
          )
        ) : null
      },
      A ? je : Dt
    ), Mt = e.createElement(
      "div",
      { style: { marginBottom: 16 } },
      e.createElement(
        "div",
        {
          style: {
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center"
          }
        },
        e.createElement("h2", { style: { margin: 0 } }, "A2A 远程 Agent"),
        e.createElement(
          W,
          null,
          e.createElement(
            T,
            {
              icon: $e ? e.createElement($e) : null,
              onClick: m,
              loading: d
            },
            "刷新列表"
          ),
          e.createElement(
            T,
            {
              icon: tt ? e.createElement(tt) : null,
              onClick: D
            },
            "从阿里云AgentHub导入"
          ),
          e.createElement(
            T,
            {
              type: "primary",
              icon: nt ? e.createElement(nt) : null,
              onClick: b
            },
            "注册 Agent"
          )
        )
      ),
      e.createElement(
        "div",
        {
          style: {
            marginTop: 8,
            fontSize: 12,
            color: "#8c8c8c",
            lineHeight: 1.6
          }
        },
        ze ? e.createElement(ze, {
          style: { marginRight: 4, color: "#faad14" }
        }) : null,
        "当前 A2A 功能仅支持 CloudPaw 插件连接阿里云 Skills 门户 Agent，连接其他 Agent 可能存在不兼容问题。"
      )
    ), Bt = d ? e.createElement(
      "div",
      { style: { textAlign: "center", padding: 60 } },
      e.createElement(ye, { size: "large" })
    ) : o.length === 0 ? e.createElement(Tt, {
      description: "暂无注册的远程 A2A Agent"
    }) : e.createElement(
      "div",
      {
        style: {
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
          gap: 12
        }
      },
      ...o.map(
        (r) => e.createElement(It, {
          key: r.alias || r.url,
          agent: r,
          onClick: () => E(r)
        })
      )
    ), be = Ae.length > 0, Ht = e.createElement(
      Ze,
      {
        title: be ? "导入结果" : "从阿里云AgentHub导入 Agent",
        open: P,
        onCancel: ee,
        closable: !Z || be,
        maskClosable: !Z || be,
        width: 800,
        footer: be ? e.createElement(
          W,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            T,
            { type: "primary", onClick: ee },
            "关闭"
          )
        ) : J.length > 0 ? e.createElement(
          W,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            T,
            { onClick: ee },
            "取消"
          ),
          e.createElement(
            T,
            {
              type: "primary",
              loading: Z,
              disabled: V.size === 0,
              onClick: De
            },
            `确认导入 (${V.size}/${J.length})`
          )
        ) : null
      },
      // Loading state
      Z && J.length === 0 && e.createElement(
        "div",
        {
          style: {
            textAlign: "center",
            padding: 40,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12
          }
        },
        e.createElement(ye, { size: "large" }),
        e.createElement(
          "span",
          { style: { fontSize: 13, color: t.colorTextTertiary } },
          "正在从 AgentHub 获取 Agent 列表..."
        )
      ),
      // Agent selection list (hide after import completed)
      !Z && !be && J.length > 0 && e.createElement(
        "div",
        null,
        // Header bar
        e.createElement(
          "div",
          {
            style: {
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 8,
              fontSize: 12,
              color: t.colorTextTertiary
            }
          },
          e.createElement(
            "span",
            null,
            `共 ${J.length} 个 Agent，已选 ${V.size} 个`
          ),
          e.createElement(
            W,
            { size: 4 },
            e.createElement(
              T,
              {
                size: "small",
                type: "link",
                style: { padding: 0, height: "auto" },
                onClick: v
              },
              "全选"
            ),
            e.createElement(
              T,
              {
                size: "small",
                type: "link",
                style: { padding: 0, height: "auto" },
                onClick: te
              },
              "取消全选"
            )
          )
        ),
        // Agent list
        e.createElement(
          "div",
          {
            style: {
              display: "flex",
              flexDirection: "column",
              gap: 8,
              maxHeight: 420,
              overflowY: "auto"
            }
          },
          ...J.map((r) => {
            var w;
            const h = V.has(r.url);
            return e.createElement(
              "div",
              {
                key: r.url,
                style: {
                  display: "flex",
                  gap: 8,
                  padding: 10,
                  border: h ? `1px solid ${t.colorInfo}` : `1px solid ${t.colorBorderSecondary}`,
                  borderRadius: 6,
                  cursor: N.has(r.url) ? "default" : "pointer",
                  background: N.has(r.url) ? t.colorBgLayout : h ? t.colorInfoBg : t.colorBgContainer,
                  transition: "all 0.15s ease",
                  opacity: N.has(r.url) ? 0.7 : 1
                },
                onClick: () => {
                  N.has(r.url) || ge(r.url);
                }
              },
              e.createElement(
                "div",
                { style: { flex: 1, minWidth: 0 } },
                e.createElement(
                  "div",
                  {
                    style: {
                      fontWeight: 500,
                      fontSize: 13,
                      marginBottom: 2
                    }
                  },
                  r.name || r.url
                ),
                r.description ? e.createElement(
                  "div",
                  {
                    style: {
                      fontSize: 11,
                      color: t.colorTextTertiary,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap"
                    }
                  },
                  r.description
                ) : null,
                ((w = r.skills) == null ? void 0 : w.length) > 0 ? e.createElement(
                  "div",
                  { style: { marginTop: 4 } },
                  ...r.skills.slice(0, 3).map(
                    (de, ke) => e.createElement(
                      $,
                      {
                        key: ke,
                        color: t.colorInfoHover,
                        style: {
                          fontSize: 10,
                          marginRight: 4,
                          fontWeight: 500
                        }
                      },
                      de.name
                    )
                  ),
                  r.skills.length > 3 ? e.createElement(
                    $,
                    { style: { fontSize: 10 } },
                    `+${r.skills.length - 3}`
                  ) : null
                ) : null
              ),
              N.has(r.url) ? e.createElement(
                $,
                {
                  color: t.colorSuccess,
                  style: {
                    fontWeight: 600,
                    fontSize: 11,
                    flexShrink: 0,
                    padding: "2px 8px",
                    lineHeight: "18px",
                    height: 22,
                    borderRadius: 4
                  }
                },
                "✓ 已导入"
              ) : null
            );
          })
        )
      ),
      // Import results
      be && e.createElement(
        "div",
        {
          style: {
            maxHeight: 350,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: 6
          }
        },
        ...Ae.map(
          (r, h) => e.createElement(
            "div",
            {
              key: h,
              style: {
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                borderRadius: 4,
                background: r.success ? t.colorInfoBg : t.colorErrorBg,
                border: r.success ? `1px solid ${t.colorInfo}` : `1px solid ${t.colorErrorBorder}`,
                fontSize: 12
              }
            },
            e.createElement(
              "span",
              {
                style: {
                  color: r.success ? t.colorSuccess : t.colorError,
                  fontSize: 14
                }
              },
              r.success ? "✓" : "✗"
            ),
            e.createElement(
              "span",
              {
                style: {
                  flex: 1,
                  color: r.success ? t.colorText : t.colorError
                }
              },
              r.name,
              r.error ? ` - ${r.error}` : ""
            )
          )
        )
      )
    );
    return e.createElement(
      "div",
      { style: { padding: 24 } },
      Mt,
      Bt,
      Lt,
      Ht
    );
  }
  function Rt({ data: t }) {
    var Ee, N, pe;
    const { token: n } = Ke.useToken(), o = e.useRef(null), [i, d] = C({}), g = he(() => {
      var b, E, a;
      const m = (a = (E = (b = t == null ? void 0 : t.content) == null ? void 0 : b[0]) == null ? void 0 : E.data) == null ? void 0 : a.arguments;
      if (!m) return null;
      try {
        return JSON.parse(m);
      } catch {
        return null;
      }
    }, [(pe = (N = (Ee = t == null ? void 0 : t.content) == null ? void 0 : Ee[0]) == null ? void 0 : N.data) == null ? void 0 : pe.arguments]), { toolResult: l, rawErrorText: c } = he(() => {
      var b;
      const m = t == null ? void 0 : t.content;
      if (!Array.isArray(m))
        return { toolResult: null, rawErrorText: "" };
      for (const E of m) {
        const a = (b = E == null ? void 0 : E.data) == null ? void 0 : b.output;
        if (!a) continue;
        let y = "";
        if (Array.isArray(a)) {
          const p = a.find(
            (S) => (S == null ? void 0 : S.type) === "text" && (S == null ? void 0 : S.text)
          );
          y = (p == null ? void 0 : p.text) || "";
        } else if (typeof a == "string")
          try {
            const p = JSON.parse(a);
            if (typeof p == "object" && (p != null && p.steps || p != null && p.response_text))
              return { toolResult: p, rawErrorText: "" };
            if (Array.isArray(p)) {
              const S = p.find((k) => (k == null ? void 0 : k.type) === "text" && (k == null ? void 0 : k.text));
              S != null && S.text && (y = S.text);
            }
          } catch {
            y = a;
          }
        if (y)
          try {
            return { toolResult: JSON.parse(y), rawErrorText: "" };
          } catch {
            return { toolResult: null, rawErrorText: y };
          }
      }
      return { toolResult: null, rawErrorText: "" };
    }, [t == null ? void 0 : t.content]), s = (l == null ? void 0 : l.steps) || [], I = (l == null ? void 0 : l.task_state) || "", A = (l == null ? void 0 : l.error) || "", _ = (l == null ? void 0 : l.response_text) || "", F = (l == null ? void 0 : l.context_id) || "";
    e.useEffect(() => {
      o.current && (o.current.scrollTop = o.current.scrollHeight);
    }, [s.length, _, c]), e.useEffect(() => {
      const m = { ...i };
      let b = !1;
      s.forEach((E, a) => {
        i[a] === void 0 && (E.type === "thinking" && E.done || E.type === "tool_call" && E.status !== "running") && (m[a] = !0, b = !0);
      }), b && d(m);
    }, [s]);
    const ne = (g == null ? void 0 : g.agent_alias) || "", M = (g == null ? void 0 : g.agent_url) || "", B = ne || M || "远程 Agent", H = {
      completed: { color: "#52c41a", text: "已完成" },
      TASK_STATE_COMPLETED: { color: "#52c41a", text: "已完成" },
      failed: { color: "#ff4d4f", text: "失败" },
      TASK_STATE_FAILED: { color: "#ff4d4f", text: "失败" },
      error: { color: "#ff4d4f", text: "出错" },
      canceled: { color: "#faad14", text: "已取消" },
      TASK_STATE_CANCELED: { color: "#faad14", text: "已取消" },
      AWAITING_USER_INPUT: { color: "#1677ff", text: "等待输入" },
      input_required: { color: "#1677ff", text: "等待输入" }
    }, x = (l !== null || !!c) && !(I === "working" || I === "TASK_STATE_WORKING");
    let f = "#1677ff", P = "执行中...";
    x && (H[I] ? (f = H[I].color, P = H[I].text) : c ? (f = "#ff4d4f", P = "出错") : (f = "#52c41a", P = "已完成"));
    const Se = e.createElement(
      W,
      { size: 6 },
      e.createElement("span", { style: { fontSize: 13 } }, "🔗"),
      e.createElement(
        G,
        { style: { fontSize: 12, color: "#595959" } },
        `A2A: ${B}`
      ),
      e.createElement(
        $,
        { color: f, style: { fontSize: 11, lineHeight: "18px" } },
        P
      )
    ), Z = F ? e.createElement(
      "div",
      {
        style: {
          fontSize: 10,
          fontFamily: "monospace",
          maxWidth: "100%",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          lineHeight: "16px",
          padding: "2px 8px",
          borderRadius: 4,
          marginBottom: 6,
          background: n.colorBgLayout,
          color: n.colorTextSecondary
        }
      },
      `contextId: ${F}`
    ) : null, ue = [Se, Z], J = s.length === 0 && !c && !A, fe = !x && J ? e.createElement(
      "div",
      {
        style: {
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 10px",
          marginBottom: 8,
          background: "#f6ffed",
          border: "1px solid #b7eb8f",
          borderRadius: 6
        }
      },
      e.createElement(ye, { size: "small" }),
      e.createElement(
        G,
        { style: { fontSize: 12, color: "#52c41a" } },
        `正在连接 ${B}...`
      )
    ) : null;
    function V(m) {
      d((b) => ({
        ...b,
        [m]: !b[m]
      }));
    }
    function re(m, b) {
      const E = !!i[b];
      if (m.type === "thinking") {
        const a = !!m.done, y = a ? "💭" : "🧠", p = a ? "思考完成" : "思考中...", S = e.createElement(
          "div",
          {
            key: `step-${b}`,
            style: {
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: a ? "pointer" : "default",
              fontSize: 12,
              color: "#8c8c8c"
            },
            onClick: a ? () => V(b) : void 0
          },
          a && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            E ? "▶" : "▼"
          ),
          e.createElement("span", null, y),
          e.createElement("span", null, p),
          !a && e.createElement(ye, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return E ? S : e.createElement(
          "div",
          { key: `step-${b}` },
          S,
          e.createElement(
            "div",
            {
              style: {
                marginLeft: 20,
                padding: "4px 8px",
                background: "#fafafa",
                borderRadius: 4,
                fontSize: 12,
                color: "#595959",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                maxHeight: 120,
                overflowY: "auto",
                lineHeight: "1.5"
              }
            },
            m.text || ""
          )
        );
      }
      if (m.type === "tool_call") {
        const a = m.status === "running", y = m.status === "error", p = a ? "⚙️" : y ? "❌" : "✅", S = a ? `正在执行: ${m.name}` : y ? `执行失败: ${m.name}` : `执行完成: ${m.name}`, k = a ? "#1677ff" : y ? "#ff4d4f" : "#52c41a", ce = e.createElement(
          "div",
          {
            key: `step-${b}`,
            style: {
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: a ? "default" : "pointer",
              fontSize: 12,
              color: k
            },
            onClick: a ? void 0 : () => V(b)
          },
          !a && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            E ? "▶" : "▼"
          ),
          e.createElement("span", null, p),
          e.createElement("span", null, S),
          a && e.createElement(ye, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return E || !m.desc && !a ? ce : e.createElement(
          "div",
          { key: `step-${b}` },
          ce,
          m.desc && e.createElement(
            "div",
            {
              style: {
                marginLeft: 20,
                padding: "2px 8px",
                fontSize: 11,
                color: "#8c8c8c"
              }
            },
            m.desc
          )
        );
      }
      return m.type === "text" ? e.createElement(
        "div",
        {
          key: `step-${b}`,
          style: {
            padding: "4px 0",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: "1.6",
            color: "#262626"
          }
        },
        m.text || ""
      ) : null;
    }
    const Ae = s.length > 0 ? e.createElement(
      "div",
      {
        ref: o,
        style: {
          background: "#fafafa",
          border: "1px solid #e8e8e8",
          borderRadius: 6,
          padding: "6px 10px",
          maxHeight: 200,
          overflowY: "auto"
        }
      },
      ...s.map(re)
    ) : null, me = c || A ? e.createElement(
      "div",
      {
        style: {
          background: "#fff2f0",
          border: "1px solid #ffccc7",
          borderRadius: 6,
          padding: "8px 12px",
          fontSize: 12,
          color: "#ff4d4f",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word"
        }
      },
      A ? `错误: ${A}` : c
    ) : null, oe = !s.length && _ && !c ? e.createElement(
      "div",
      {
        ref: o,
        style: {
          background: "#fafafa",
          border: "1px solid #e8e8e8",
          borderRadius: 6,
          padding: "10px 12px",
          maxHeight: 200,
          overflowY: "auto"
        }
      },
      e.createElement(
        G,
        {
          style: {
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: "1.6"
          }
        },
        _
      )
    ) : null;
    return e.createElement(
      "div",
      {
        style: {
          width: "100%",
          borderRadius: 8,
          border: "1px solid #f0f0f0",
          overflow: "hidden",
          background: "#fff",
          padding: "8px 12px",
          margin: "4px 0"
        }
      },
      e.createElement(
        "div",
        { style: { marginBottom: 6 } },
        ...ue
      ),
      fe,
      Ae,
      oe,
      me
    );
  }
  const Pt = "__A2A_STREAM_START__", Ot = "A2A_STREAM_START", ve = /* @__PURE__ */ new Set();
  function Me(t) {
    return t ? t.includes(Pt) || t.includes(Ot) : !1;
  }
  function Be(t) {
    var n, o;
    return t.getAttribute("data-msg-id") || t.getAttribute("data-message-id") || ((n = t.closest("[data-msg-id]")) == null ? void 0 : n.getAttribute("data-msg-id")) || ((o = t.closest("[data-message-id]")) == null ? void 0 : o.getAttribute("data-message-id")) || null;
  }
  function $t(t) {
    if (Me(t.innerHTML) || Me(t.textContent))
      return t;
    const n = document.createTreeWalker(
      t,
      NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT
    );
    for (; n.nextNode(); ) {
      const o = n.currentNode, i = o.nodeType === Node.TEXT_NODE ? o.textContent : o.innerHTML;
      if (Me(i)) {
        const d = o.nodeType === Node.TEXT_NODE ? o.parentElement : o;
        if (d) return d;
      }
    }
    return null;
  }
  async function He(t) {
    var s, I;
    const n = window.QwenPaw;
    if (!(n != null && n.host)) {
      console.warn("[a2a] QwenPaw.host not available");
      return;
    }
    const { getApiUrl: o, getApiToken: i } = n.host, d = o("/a2a/call/stream"), g = i();
    console.log("[a2a] Subscribing to SSE stream:", d);
    const l = document.createElement("div");
    l.style.cssText = "background:#f6ffed;border:1px solid #b7eb8f;border-radius:8px;padding:12px 16px;margin:4px 0;font-size:13px;white-space:pre-wrap;word-break:break-word;color:#262626;min-height:24px;", l.textContent = "正在连接远程 Agent...", t.textContent = "", t.appendChild(l);
    const c = new AbortController();
    try {
      const A = {
        Accept: "text/event-stream"
      };
      g && (A.Authorization = `Bearer ${g}`);
      try {
        const B = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage"), H = (I = (s = JSON.parse(B || "{}")) == null ? void 0 : s.state) == null ? void 0 : I.selectedAgent;
        H && (A["X-Agent-Id"] = H);
      } catch {
      }
      console.log("[a2a] Fetching SSE with headers:", A);
      const _ = await fetch(d, { headers: A, signal: c.signal });
      if (console.log("[a2a] SSE response status:", _.status), !_.ok) {
        const B = await _.text().catch(() => "");
        l.textContent = `SSE 连接失败 (${_.status}): ${B.slice(
          0,
          100
        )}`, l.style.borderColor = "#ff4d4f", l.style.background = "#fff1f0";
        return;
      }
      if (!_.body) {
        l.textContent = "SSE 连接失败：无响应体", l.style.borderColor = "#ff4d4f", l.style.background = "#fff1f0";
        return;
      }
      const F = _.body.getReader(), ne = new TextDecoder();
      let M = "";
      for (; ; ) {
        const { done: B, value: H } = await F.read();
        if (B) {
          console.log("[a2a] SSE stream ended (done)");
          break;
        }
        M += ne.decode(H, { stream: !0 });
        const R = M.split(`
`);
        M = R.pop() || "";
        for (const u of R)
          if (u.startsWith("data: "))
            try {
              const x = JSON.parse(u.slice(6));
              if (console.log("[a2a] SSE event:", x), x.done) {
                x.error && (l.textContent = `错误: ${x.error}`, l.style.borderColor = "#ff4d4f", l.style.background = "#fff1f0"), console.log("[a2a] SSE done signal received");
                return;
              }
              typeof x.response_text == "string" && x.response_text && (l.textContent = x.response_text);
            } catch (x) {
              console.warn("[a2a] SSE parse error:", x, "line:", u);
            }
      }
    } catch (A) {
      (A == null ? void 0 : A.name) !== "AbortError" && (console.error("[a2a] SSE subscription error:", A), l.textContent = `连接出错: ${(A == null ? void 0 : A.message) || A}`, l.style.borderColor = "#ff4d4f", l.style.background = "#fff1f0");
    }
  }
  function Nt() {
    console.log("[a2a] Initializing stream interceptor");
    function t(d) {
      if (d.nodeType !== Node.ELEMENT_NODE) return;
      const g = d, l = Be(g);
      if (l && ve.has(l)) return;
      const c = $t(g);
      c && (console.log("[a2a] Marker detected in DOM, msgId:", l), l && ve.add(l), He(c));
    }
    new MutationObserver((d) => {
      for (const g of d) {
        for (const l of g.addedNodes)
          t(l);
        g.target.nodeType === Node.ELEMENT_NODE && t(g.target);
      }
    }).observe(document.body, {
      childList: !0,
      subtree: !0,
      characterData: !0,
      characterDataOldValue: !0
    });
    const o = setInterval(() => {
      const d = document.evaluate(
        "//text()[contains(., 'A2A_STREAM_START')]",
        document.body,
        null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
        null
      );
      for (let g = 0; g < d.snapshotLength; g++) {
        const c = d.snapshotItem(g).parentElement;
        if (c) {
          const s = Be(c);
          if (s && ve.has(s)) continue;
          console.log("[a2a] Marker found in periodic scan, msgId:", s), s && ve.add(s), He(c);
        }
      }
    }, 500);
    window.addEventListener("beforeunload", () => clearInterval(o));
    const i = document.evaluate(
      "//text()[contains(., 'A2A_STREAM_START')]",
      document.body,
      null,
      XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
      null
    );
    for (let d = 0; d < i.snapshotLength; d++) {
      const l = i.snapshotItem(d).parentElement;
      if (l) {
        const c = Be(l);
        c && ve.add(c), console.log("[a2a] Marker found in existing DOM, msgId:", c), He(l);
      }
    }
  }
  (ct = (it = window.QwenPaw).registerToolRender) == null || ct.call(it, "cloudpaw", {
    proposal_choice: bt,
    manage_prd: kt,
    a2a_call: Rt
  }), (ut = (dt = window.QwenPaw).registerRoutes) == null || ut.call(dt, "cloudpaw", [
    {
      path: "/a2a",
      component: zt,
      label: "A2A",
      icon: "🔗",
      priority: 10
    }
  ]);
  const st = {
    zh: "查看或调用已注册的远程 A2A Agent",
    en: "View or call registered remote A2A agents",
    ja: "登録済みのリモート A2A エージェントを表示または呼び出す",
    ru: "Просмотр или вызов зарегистрированных удалённых агентов A2A",
    id: "Lihat atau panggil agen A2A jarak jauh yang terdaftar",
    pt: "Ver ou chamar agentes A2A remotos registrados"
  };
  function at() {
    var n, o;
    const t = (() => {
      const i = localStorage.getItem("language") || "";
      return i ? i.split("-")[0] : (navigator.language || "en").split("-")[0];
    })();
    (o = (n = window.QwenPaw).registerCommandSuggestions) == null || o.call(n, "cloudpaw", [
      {
        command: "/a2a",
        description: st[t] || st.en
      }
    ]);
  }
  at(), window.addEventListener("qwenpaw:language-change", () => {
    at();
  }), Ft(), Jt(), Nt();
}
function Ft() {
  const e = "qwenpaw-last-used-agent", j = "qwenpaw-agent-storage", Y = "cloudpaw-first-install", q = "cloud-orchestrator";
  if (localStorage.getItem(Y)) return;
  localStorage.setItem(Y, "true");
  function U() {
    localStorage.setItem(e, q);
    try {
      const X = localStorage.getItem(j);
      if (X) {
        const L = JSON.parse(X);
        L.state = L.state || {}, L.state.selectedAgent = q, localStorage.setItem(j, JSON.stringify(L));
      } else
        localStorage.setItem(
          j,
          JSON.stringify({
            version: 0,
            state: {
              selectedAgent: q,
              agents: [],
              lastChatIdByAgent: {}
            }
          })
        );
    } catch {
    }
    try {
      const X = sessionStorage.getItem(j);
      if (X) {
        const L = JSON.parse(X);
        L.state = L.state || {}, L.state.selectedAgent = q, sessionStorage.setItem(j, JSON.stringify(L));
      } else
        sessionStorage.setItem(
          j,
          JSON.stringify({
            version: 0,
            state: {
              selectedAgent: q,
              agents: [],
              lastChatIdByAgent: {}
            }
          })
        );
    } catch {
    }
  }
  U(), window.addEventListener(
    "beforeunload",
    () => {
      U();
    },
    { once: !0 }
  ), console.info(
    "[cloudpaw] Set default agent to cloud-orchestrator for first-time user"
  ), window.location.reload();
}
function Jt() {
  var W;
  const e = (W = window.QwenPaw) == null ? void 0 : W.modules;
  if (!e) return;
  const j = e["Chat/OptionsPanel/defaultConfig"];
  if (!(j != null && j.configProvider)) {
    console.warn(
      "[cloudpaw] configProvider not found — skipping welcome/theme patch"
    );
    return;
  }
  const Y = j.configProvider, q = Y.getConfig.bind(Y), U = "https://gw.alicdn.com/imgextra/i2/O1CN01pyXzjQ1EL1PuZMlSd_!!6000000000334-2-tps-288-288.png", X = {
    zh: "CloudPaw 插件提示",
    en: "CloudPaw Plugin Tips",
    ja: "CloudPaw プラグインのヒント",
    ru: "Подсказки плагина CloudPaw"
  }, L = {
    zh: `告诉 CloudPaw 你想做什么，它会自动帮你完成云资源管理、基础设施编排与应用创建上云等任务。
⚠️ 使用前请在左上角下拉框切换到「CloudPaw-Master」，否则功能无法正常使用！
对于复杂的长程任务，建议使用 /mission 命令启动 Mission Mode 来自动拆解和执行。`,
    en: `Tell CloudPaw what you want to do — it will automatically handle cloud resource management, infrastructure orchestration, and application deployment.
⚠️ Please switch to 'CloudPaw-Master' from the dropdown in the top-left corner before use — features won't work otherwise!
For complex, multi-step tasks, use /mission to start Mission Mode for automated decomposition and execution.`,
    ja: `CloudPaw にやりたいことを伝えるだけで、クラウドリソース管理、インフラ構成、アプリケーションのデプロイなどを自動で行います。
⚠️ 使用前に左上のドロップダウンから「CloudPaw-Master」に切り替えてください。切り替えないと機能が正常に動作しません！
複雑なタスクには /mission コマンドで Mission Mode を起動し、自動分解・実行できます。`,
    ru: `Расскажите CloudPaw, что вы хотите сделать — он автоматически выполнит управление облачными ресурсами, оркестрацию инфраструктуры и развёртывание приложений.
⚠️ Перед началом переключитесь на 'CloudPaw-Master' в выпадающем списке в левом верхнем углу — иначе функции не будут работать!
Для сложных задач используйте /mission для автоматической декомпозиции и выполнения.`
  }, $ = {
    zh: [
      {
        label: "创建个人主页并部署到云端",
        value: "/mission 帮我创建一个个人主页并上线到云端。页面包含：个人介绍、技能展示、项目经历、联系方式，所有个人信息请先用占位符代替。风格简洁清爽，适配手机和电脑。请使用阿里云 ECS 部署。"
      },
      {
        label: "快速发布 API 服务到云端",
        value: "/mission 帮我把一个 API 服务快速发布到云端。我希望默认提供 /health 和 /hello 两个接口，并给我可直接调用的地址和示例请求，配置尽量简单清晰。"
      }
    ],
    en: [
      {
        label: "Create a personal homepage and deploy to the cloud",
        value: "/mission Help me create a personal homepage and deploy it to the cloud. The page should include: personal introduction, skills, project experience, and contact info — please use placeholders for all personal information. The style should be clean and minimal, responsive for mobile and desktop. Please deploy using Alibaba Cloud ECS."
      },
      {
        label: "Deploy an API service to the cloud",
        value: "/mission Help me quickly deploy an API service to the cloud. I want it to provide /health and /hello endpoints by default, and give me a callable URL with example requests. Keep the configuration as simple and clean as possible."
      }
    ]
  };
  function Ce() {
    const T = localStorage.getItem("language") || "";
    return T ? T.split("-")[0] : (navigator.language || "").split("-")[0] || "en";
  }
  if (Y.getGreeting = () => X[Ce()] || X.en, Y.getDescription = () => L[Ce()] || L.en, Y.getPrompts = () => $[Ce()] || $.en, Y.getConfig = function(T) {
    var Te;
    const Q = q(T);
    return {
      ...Q,
      theme: {
        ...Q.theme,
        leftHeader: {
          ...(Te = Q.theme) == null ? void 0 : Te.leftHeader,
          title: "Work with CloudPaw"
        }
      },
      welcome: {
        ...Q.welcome,
        avatar: U
      }
    };
  }, !document.getElementById("cloudpaw-welcome-style")) {
    const T = document.createElement("style");
    T.id = "cloudpaw-welcome-style", T.textContent = `
      [class*="chat-anywhere-welcome-default"] [class*="description"],
      [class*="message-list-welcome"] [class*="description"] {
        white-space: pre-line !important;
        text-align: center !important;
      }
    `, document.head.appendChild(T);
  }
  console.info("[cloudpaw] Patched welcome config & theme via configProvider");
}
Wt();
