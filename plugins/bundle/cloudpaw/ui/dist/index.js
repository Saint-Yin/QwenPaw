function Mt() {
  var ot, lt, st, at;
  const { React: e, antd: F, antdIcons: Y, getApiUrl: q, getApiToken: U } = window.QwenPaw.host, {
    Card: G,
    Table: W,
    Tag: D,
    Typography: be,
    Space: J,
    Button: b,
    Input: te,
    Radio: ke,
    Collapse: Bt,
    Descriptions: ie,
    Tooltip: Fe,
    Spin: ye,
    message: Je
  } = F, { Text: X } = be, { TextArea: ut } = te, { useState: C, useMemo: he, useCallback: L, useRef: Ht } = e, {
    InfoCircleOutlined: ze,
    DownOutlined: Ke,
    RightOutlined: ft,
    CheckCircleOutlined: Pe,
    FieldTimeOutlined: Oe,
    FileTextOutlined: Ue
  } = Y || {};
  function Ye(t) {
    var i, a;
    const n = (a = (i = t == null ? void 0 : t.content) == null ? void 0 : i[0]) == null ? void 0 : a.data, l = n == null ? void 0 : n.arguments;
    if (typeof l == "string")
      try {
        return JSON.parse(l);
      } catch {
        return {};
      }
    return l ?? {};
  }
  function mt() {
    return window.currentSessionId ?? null;
  }
  function ce(t) {
    return typeof t == "string" ? t : t && typeof t == "object" && "text" in t ? t.text : String(t ?? "");
  }
  function pt(t) {
    if (t == null) return !0;
    const n = ce(t).trim();
    return !!(!n || /^[¥$]?0+(\.0+)?$/.test(n) || /^[-–—]+$/.test(n));
  }
  async function gt(t, n) {
    try {
      const l = U(), i = {
        "Content-Type": "application/json"
      };
      return l && (i.Authorization = `Bearer ${l}`), (await fetch(q("/interaction"), {
        method: "POST",
        headers: i,
        body: JSON.stringify({ session_id: t, result: n })
      })).ok;
    } catch {
      return !1;
    }
  }
  function qe(t) {
    if (!t) return null;
    if (typeof t == "string")
      try {
        const n = JSON.parse(t);
        if (Array.isArray(n)) {
          const l = n.find(
            (i) => (i == null ? void 0 : i.type) === "text" && (i == null ? void 0 : i.text)
          );
          return (l == null ? void 0 : l.text) ?? null;
        }
        if (typeof n == "string") return n;
      } catch {
        return t;
      }
    if (Array.isArray(t)) {
      const n = t.find((l) => (l == null ? void 0 : l.type) === "text" && (l == null ? void 0 : l.text));
      return (n == null ? void 0 : n.text) ?? null;
    }
    return null;
  }
  function yt(t) {
    var s, r;
    if (!t || t.length < 2) return null;
    const n = (r = (s = t[1]) == null ? void 0 : s.data) == null ? void 0 : r.output, l = qe(n);
    if (!l) return null;
    if (l.startsWith("Error:")) return l;
    const i = l.match(/^用户选择了「(.+?)」并确认部署$/);
    if (i) return `已确认部署「${i[1]}」`;
    const a = l.match(
      /^用户选择「(.+?)」并要求调整[：:](.+)$/
    );
    if (a)
      return `已选择「${a[1]}」并调整：${a[2]}`;
    if (l === "用户确认部署") return "已确认部署";
    const d = l.match(/^用户要求调整资源[：:](.+)$/);
    return d ? `已反馈调整意见：${d[1]}` : "已确认";
  }
  const Ge = [
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
  ], ht = new Set(
    Ge.map((t) => t.toLowerCase())
  );
  function Le(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = ce(t[0]).trim().toLowerCase();
    return ht.has(n);
  }
  function Xe(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = ce(t[0]).trim();
    return /^(合计|总计|total)/i.test(n);
  }
  function Et(t) {
    const n = [];
    let l = [];
    for (const i of t)
      l.push(i), Xe(i) && (n.push(l), l = []);
    return l.length > 0 && (n.length > 0 ? n[n.length - 1].push(...l) : n.push(l)), n.length > 0 ? n : [t];
  }
  function xt(t) {
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
  function wt({ data: t }) {
    var g, T, k;
    const [n, l] = C("confirm"), [i, a] = C(""), [d, s] = C(!1), [r, w] = C(null), [z, A] = C(
      {}
    ), B = e.useRef(!1), K = e.useRef(null), [, re] = C(0), P = t == null ? void 0 : t.content, I = P && P.length >= 2 && ((T = (g = P[1]) == null ? void 0 : g.data) == null ? void 0 : T.output), Q = he(
      () => yt(P),
      [P]
    ), O = B.current || I || Q !== null, c = he(() => {
      const m = Ye(t), h = m == null ? void 0 : m.data;
      if (!h) return null;
      try {
        const x = typeof h == "string" ? JSON.parse(h) : h;
        let R;
        if (m.strategy_names)
          try {
            const M = typeof m.strategy_names == "string" ? JSON.parse(m.strategy_names) : m.strategy_names;
            R = Array.isArray(M) ? M : [];
          } catch {
            R = [];
          }
        else x != null && x.proposal_names ? R = x.proposal_names : R = [];
        const le = R.length >= 2 ? R.length : 0;
        let N;
        if (Array.isArray(x) && x.length > 0)
          if (Array.isArray(x[0]) && x[0].length === 10 && !Array.isArray(x[0][0])) {
            const j = x.filter(
              (ae) => !Le(ae)
            );
            if (j.filter(
              (ae) => Xe(ae)
            ).length >= 2)
              N = Et(j);
            else if (le >= 2 && j.length >= le * 2) {
              const ae = Math.ceil(j.length / le);
              N = [];
              for (let ge = 0; ge < j.length; ge += ae)
                N.push(j.slice(ge, ge + ae));
            } else
              N = [j];
          } else
            N = x.map(
              (j) => j.filter(
                (se) => Array.isArray(se) && se.length === 10 && !Le(se)
              )
            );
        else if (x != null && x.proposals)
          N = x.proposals.map(
            (M) => M.filter((j) => !Le(j))
          );
        else
          return null;
        if (N = N.filter((M) => M.length > 0), N.length === 0) return null;
        const we = ["方案一", "方案二", "方案三", "方案四", "方案五"];
        if (R.length < N.length)
          for (let M = R.length; M < N.length; M++)
            R.push(we[M] || `方案${M + 1}`);
        return { proposals: N, names: R };
      } catch {
        return null;
      }
    }, [t]), f = mt(), u = (((k = c == null ? void 0 : c.proposals) == null ? void 0 : k.length) ?? 0) > 1, H = L(async () => {
      if (!f || O || !c) return;
      const m = u ? r : 0, h = c.names[m ?? 0] || `方案${(m ?? 0) + 1}`;
      let x;
      n === "confirm" ? x = `用户选择了「${h}」并确认部署` : x = `用户选择「${h}」并要求调整：${i.trim() || "未填写具体要求"}`, s(!0);
      const R = await gt(f, x);
      s(!1), R ? (B.current = !0, n === "confirm" ? K.current = `已确认部署「${h}」` : K.current = `已选择「${h}」并调整：${i.trim()}`, re((le) => le + 1), Je.success(
        n === "confirm" ? "已确认部署方案" : "已提交调整意见"
      )) : Je.error("操作失败，请重试");
    }, [
      f,
      O,
      c,
      n,
      i,
      r,
      u
    ]), oe = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created";
    if (!c)
      return oe ? e.createElement(
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
          X,
          { type: "secondary", style: { fontSize: 13 } },
          "正在生成资源方案..."
        )
      ) : e.createElement(
        G,
        { size: "small", style: { margin: "4px 0" } },
        e.createElement(X, { type: "secondary" }, "无法解析方案数据")
      );
    const { proposals: V, names: xe } = c, me = Ge.map((m, h) => ({
      title: m,
      dataIndex: `col_${h}`,
      key: `col_${h}`,
      render: (x) => xt(x),
      ellipsis: h < 3
    }));
    let ue = "待确认", fe = "processing";
    O && (fe = "success", ue = K.current || Q || "已确认");
    const Z = e.createElement(
      D,
      {
        color: fe,
        style: { marginLeft: 4 }
      },
      ue
    ), pe = e.createElement(
      J,
      { size: 8 },
      e.createElement("span", null, "☁️"),
      e.createElement(
        X,
        { strong: !0, style: { fontSize: 14 } },
        O ? "资源配置方案" : "请确认您的资源配置方案"
      ),
      Z
    ), $ = V.map((m, h) => {
      const x = u ? r === h : !0, R = z[h] || !1, le = (v) => {
        const ee = ce(v[0] || "").trim();
        return /^合计|^总计|^total/i.test(ee);
      }, N = m.find(le), we = m.filter((v) => !le(v)), M = we.map((v) => ({
        type: ce(v[0] || ""),
        purpose: ce(v[1] || ""),
        spec: ce(v[2] || ""),
        cost: v[9] ?? null
      })), j = N ? ce(N[9] ?? "") : "", se = m.map((v, ee) => {
        const De = { key: ee };
        return v.forEach((Ee, Ie) => {
          De[`col_${Ie}`] = Ee;
        }), De;
      }), ae = x ? "2px solid #1677ff" : "1px solid #e8e8e8", ge = x ? "0 0 0 2px #e6f4ff" : "none";
      return e.createElement(
        "div",
        {
          key: h,
          style: {
            flex: 1,
            minWidth: 240,
            border: ae,
            borderRadius: 8,
            cursor: u ? "pointer" : "default",
            transition: "all 0.2s ease",
            boxShadow: ge,
            background: "#fff"
          },
          onClick: u ? () => w(h) : void 0
        },
        e.createElement(
          "div",
          { style: { padding: "10px 12px" } },
          // Proposal name
          e.createElement(
            X,
            {
              strong: !0,
              style: { fontSize: 14, display: "block", marginBottom: 8 }
            },
            xe[h]
          ),
          ...M.map(
            (v, ee) => e.createElement(
              "div",
              {
                key: ee,
                style: {
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "4px 0",
                  borderBottom: ee < M.length - 1 ? "1px solid #f5f5f5" : "none"
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
              !pt(v.cost) && e.createElement(
                "span",
                {
                  style: {
                    fontSize: 12,
                    color: "#595959",
                    flexShrink: 0,
                    marginLeft: 8
                  }
                },
                ce(v.cost)
              )
            )
          ),
          // Total cost
          j && e.createElement(
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
              j
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
                v.stopPropagation(), A((ee) => ({
                  ...ee,
                  [h]: !ee[h]
                }));
              }
            },
            e.createElement(
              R && Ke ? Ke : ft || "span",
              {
                style: { fontSize: 10 }
              }
            ),
            e.createElement(
              "span",
              null,
              `明细 · ${we.length} 项`
            )
          ),
          R && e.createElement(
            "div",
            {
              onClick: (v) => v.stopPropagation(),
              style: { marginTop: 4, maxHeight: 260, overflow: "auto" }
            },
            e.createElement(W, {
              columns: me,
              dataSource: se,
              pagination: !1,
              size: "small",
              scroll: { x: "max-content" }
            })
          )
        )
      );
    }), y = e.createElement(
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
    ), p = !O && f && !(u && r === null) && e.createElement(
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
            onClick: () => l("confirm")
          },
          e.createElement(ke, { checked: n === "confirm" }),
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
              onClick: () => l("adjust")
            },
            e.createElement(ke, { checked: n === "adjust" }),
            e.createElement(
              "span",
              { style: { fontSize: 13 } },
              "调整资源"
            )
          ),
          n === "adjust" && e.createElement(ut, {
            value: i,
            onChange: (m) => a(m.target.value),
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
          X,
          { type: "secondary", style: { fontSize: 11 } },
          u ? "一小时后未操作将自动选择第一个方案" : "一小时后未操作将自动确认部署"
        ),
        e.createElement(
          b,
          {
            type: "primary",
            size: "small",
            loading: d,
            onClick: H,
            disabled: n === "adjust" && !i.trim()
          },
          n === "confirm" ? "确认部署" : "提交调整"
        )
      )
    ), _ = u && r === null && !O && e.createElement(
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
      e.createElement("div", { style: { marginBottom: 10 } }, pe),
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
        ...$
      ),
      _,
      y,
      !O && p
    );
  }
  function St({ data: t }) {
    const [n, l] = C(null), [i, a] = C(!1), d = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created", s = he(() => {
      const c = Ye(t);
      return (c == null ? void 0 : c.loop_dir) || null;
    }, [t]), r = he(() => {
      var f, u, H;
      const c = qe((H = (u = (f = t == null ? void 0 : t.content) == null ? void 0 : f[1]) == null ? void 0 : u.data) == null ? void 0 : H.output);
      if (!c) return null;
      try {
        return JSON.parse(c);
      } catch {
        return null;
      }
    }, [t]), w = (r == null ? void 0 : r.status) === "ok", z = (r == null ? void 0 : r.status) === "error", A = z ? (r == null ? void 0 : r.message) || "未知错误" : null, B = L(async () => {
      if (s)
        try {
          const c = U(), f = {};
          c && (f.Authorization = `Bearer ${c}`);
          const u = await fetch(
            q(`/prd?loop_dir=${encodeURIComponent(s)}`),
            { headers: f }
          );
          if (!u.ok) {
            a(!0);
            return;
          }
          const H = await u.json();
          H && Array.isArray(H.userStories) ? (l(H), a(!1)) : a(!0);
        } catch {
          a(!0);
        }
    }, [s]);
    if (e.useEffect(() => {
      !d && w && s && B();
    }, [d, w, s, B]), d)
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
          X,
          { type: "secondary", style: { fontSize: 13 } },
          "正在更新 PRD..."
        )
      );
    if (z)
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
          X,
          { type: "danger", style: { fontSize: 13 } },
          `PRD 格式错误，将会修正：${A}`
        )
      );
    if (!w || i || !n) return null;
    const K = n.userStories, re = [...K].sort(
      (c, f) => (c.priority || 99) - (f.priority || 99)
    ), P = K.filter((c) => c.passes).length, I = [
      {
        title: "状态",
        key: "status",
        width: 50,
        align: "center",
        render: (c, f) => {
          if (f.passes) {
            const H = Pe ? e.createElement(Pe, {
              style: { color: "#52c41a", fontSize: 18 }
            }) : "✅";
            return e.createElement(Fe, { title: "已完成" }, H);
          }
          const u = Oe ? e.createElement(Oe, {
            style: { color: "#faad14", fontSize: 18 }
          }) : "🕐";
          return e.createElement(Fe, { title: "待处理" }, u);
        }
      },
      {
        title: "ID",
        dataIndex: "id",
        key: "id",
        width: 85,
        render: (c) => e.createElement(D, { color: "blue" }, c)
      },
      {
        title: "标题",
        dataIndex: "title",
        key: "title",
        render: (c) => e.createElement(X, { strong: !0 }, c)
      },
      {
        title: "优先级",
        key: "priority",
        width: 70,
        render: (c, f) => {
          const u = f.priority;
          return e.createElement(
            D,
            { color: "default" },
            u != null ? String(u) : "-"
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
        render: (c, f) => {
          const u = f.acceptanceCriteria;
          return typeof u == "string" ? e.createElement(
            "div",
            {
              style: { fontSize: 12, color: "#666", whiteSpace: "pre-wrap" }
            },
            u.length > 100 ? u.slice(0, 100) + "..." : u
          ) : Array.isArray(u) ? e.createElement(
            "div",
            { style: { fontSize: 12, color: "#666" } },
            u.length > 2 ? u.slice(0, 2).join(", ") + "..." : u.join(", ")
          ) : "-";
        }
      }
    ], Q = e.createElement(
      J,
      { size: 8 },
      Ue ? e.createElement(Ue, { style: { color: "#1677ff" } }) : null,
      e.createElement(
        "span",
        { style: { fontSize: 14 } },
        e.createElement(X, { strong: !0 }, n.project || "PRD")
      )
    ), O = e.createElement(W, {
      columns: I,
      dataSource: re.map((c) => ({ ...c, key: c.id })),
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
      e.createElement("div", { style: { marginBottom: 8 } }, Q),
      e.createElement(ie, {
        size: "small",
        column: { xs: 1, sm: 2, md: 3 },
        style: { marginBottom: 12 },
        bordered: !1,
        items: [
          {
            key: "progress",
            label: "进度",
            children: `${P}/${K.length} 完成`
          }
        ]
      }),
      O,
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
        Pe ? e.createElement(Pe, {
          style: { color: "#52c41a", fontSize: 14 }
        }) : "✅",
        e.createElement("span", null, "已完成"),
        e.createElement("span", { style: { margin: "0 4px" } }, "·"),
        Oe ? e.createElement(Oe, {
          style: { color: "#faad14", fontSize: 14 }
        }) : "🕐",
        e.createElement("span", null, "待处理")
      )
    );
  }
  const {
    Form: de,
    Select: $e,
    Drawer: At,
    Modal: Qe,
    Empty: bt,
    Badge: Ve,
    Divider: kt,
    message: ne
  } = F, {
    ApiOutlined: Ze,
    PlusOutlined: et,
    ReloadOutlined: Ne,
    DeleteOutlined: tt,
    LinkOutlined: nt,
    DisconnectOutlined: jt
  } = Y || {}, { useEffect: rt } = e, Ce = "/a2a/agents";
  function Me() {
    var t;
    try {
      const n = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage");
      if (n) {
        const l = JSON.parse(n);
        return ((t = l == null ? void 0 : l.state) == null ? void 0 : t.selectedAgent) || null;
      }
    } catch {
    }
    return null;
  }
  async function Te(t, n) {
    const l = q(t), i = U == null ? void 0 : U(), a = Me(), d = {
      "Content-Type": "application/json",
      ...i ? { Authorization: `Bearer ${i}` } : {},
      ...a ? { "X-Agent-Id": a } : {}
    }, s = await fetch(l, {
      ...n,
      headers: { ...d, ...(n == null ? void 0 : n.headers) || {} }
    });
    if (!s.ok) {
      const r = await s.text().catch(() => "");
      throw new Error(r || `HTTP ${s.status}`);
    }
    return s.status === 204 || s.headers.get("content-length") === "0" ? null : s.json();
  }
  function Ct(t) {
    var r;
    const { agent: n, onClick: l } = t, i = n.status === "connected", a = i ? "#52c41a" : n.status === "error" ? "#ff4d4f" : "#d9d9d9", d = i ? "已连接" : n.status === "error" ? "错误" : "未连接", s = {
      gateway: "阿里云Agent Hub",
      bearer: "Bearer Token",
      api_key: "API Key"
    };
    return e.createElement(
      G,
      {
        hoverable: !0,
        onClick: l,
        size: "small",
        style: { cursor: "pointer" },
        title: e.createElement(
          J,
          null,
          e.createElement(Ve, { color: a }),
          e.createElement(
            "span",
            null,
            n.name || n.alias || n.url
          )
        ),
        extra: n.auth_type ? e.createElement(
          D,
          { color: "blue" },
          s[n.auth_type] || n.auth_type
        ) : null
      },
      e.createElement(
        "div",
        { style: { fontSize: 12, color: "#666" } },
        e.createElement(
          "div",
          { style: { marginBottom: 4 } },
          nt ? e.createElement(nt, { style: { marginRight: 4 } }) : null,
          n.url
        ),
        n.description ? e.createElement(
          "div",
          { style: { marginBottom: 4, color: "#999" } },
          n.description
        ) : null,
        ((r = n.skills) == null ? void 0 : r.length) > 0 ? e.createElement(
          "div",
          null,
          n.skills.slice(0, 3).map(
            (w, z) => e.createElement(
              D,
              { key: z, style: { fontSize: 11 } },
              w.name
            )
          ),
          n.skills.length > 3 ? e.createElement(
            D,
            { style: { fontSize: 11 } },
            `+${n.skills.length - 3}`
          ) : null
        ) : null,
        e.createElement(
          "div",
          { style: { marginTop: 4, color: a, fontSize: 11 } },
          d,
          n.error ? ` - ${n.error}` : ""
        )
      )
    );
  }
  function Tt() {
    const t = e.useRef(Me()), [n, l] = C(t.current);
    return rt(() => {
      const i = () => {
        const d = Me();
        d !== t.current && (t.current = d, l(d));
      }, a = setInterval(i, 200);
      return window.addEventListener("storage", i), () => {
        clearInterval(a), window.removeEventListener("storage", i);
      };
    }, []), n;
  }
  function vt() {
    var ct, dt;
    const t = Tt(), [n, l] = C([]), [i, a] = C(!0), [d, s] = C(!1), [r, w] = C(null), [z, A] = C(!1), [B, K] = C(!1), [re, P] = C(!1), [I] = de.useForm(), [Q, O] = C(!1), [c, f] = C(!1), [u, H] = C([]), [oe, V] = C(
      /* @__PURE__ */ new Set()
    ), [xe, me] = C([]), [ue, fe] = C(1), Z = e.useRef(null), pe = 10, $ = he(
      () => new Set(n.map((o) => o.name)),
      [n]
    ), y = e.useRef($);
    y.current = $;
    const p = L(async () => {
      a(!0);
      try {
        const o = await Te(Ce);
        l((o == null ? void 0 : o.agents) || []);
      } catch {
        l([]);
      } finally {
        a(!1);
      }
    }, []);
    rt(() => {
      p();
    }, [t]);
    const _ = L(() => {
      A(!0), w(null), s(!0), I.resetFields(), I.setFieldsValue({
        url: "",
        alias: "",
        auth_type: "",
        auth_token: ""
      });
    }, [I]), g = L((o) => {
      A(!1), w(o), s(!0);
    }, []), T = L(() => {
      s(!1), w(null), A(!1), I.resetFields();
    }, [I]), k = L(async () => {
      let o;
      try {
        o = await I.validateFields();
      } catch {
        return;
      }
      const E = {
        url: String(o.url || "").trim(),
        alias: String(o.alias || "").trim() || void 0,
        auth_type: String(o.auth_type || ""),
        auth_token: String(o.auth_token || "")
      };
      if (E.url) {
        K(!0);
        try {
          await Te(Ce, {
            method: "POST",
            body: JSON.stringify(E)
          }), ne.success("A2A Agent 注册成功"), await p(), T();
        } catch (S) {
          ne.error(S.message || "注册失败");
        } finally {
          K(!1);
        }
      }
    }, [I, p, T]), m = L(async () => {
      if (!r) return;
      const o = r.alias || r.url;
      Qe.confirm({
        title: `删除 ${o}`,
        content: "确定删除该远程 A2A Agent 吗？此操作不可撤销。",
        okText: "删除",
        cancelText: "取消",
        okButtonProps: { danger: !0 },
        async onOk() {
          try {
            await Te(`${Ce}/${encodeURIComponent(o)}`, {
              method: "DELETE"
            }), ne.success("A2A Agent 已删除"), await p(), T();
          } catch (E) {
            ne.error(E.message || "删除失败");
          }
        }
      });
    }, [r, p, T]), h = L(async () => {
      if (!r) return;
      const o = r.alias || r.url;
      P(!0);
      try {
        const E = await Te(
          `${Ce}/${encodeURIComponent(o)}/refresh`,
          {
            method: "POST"
          }
        );
        ne.success("Agent Card 已刷新"), await p(), E && w(E);
      } catch (E) {
        ne.error(E.message || "刷新失败");
      } finally {
        P(!1);
      }
    }, [r, p]), x = L(() => {
      O(!0), H([]), V(/* @__PURE__ */ new Set()), me([]), fe(1), Z.current = null, le();
    }, []), R = L(() => {
      c && Z.current && Z.current.abort(), O(!1), H([]), V(/* @__PURE__ */ new Set()), me([]), fe(1), Z.current = null;
    }, [c]), le = L(async () => {
      f(!0);
      const o = new AbortController();
      Z.current = o;
      try {
        const E = U == null ? void 0 : U(), S = Me(), Se = {
          ...E ? { Authorization: `Bearer ${E}` } : {},
          ...S ? { "X-Agent-Id": S } : {}
        }, Ae = await fetch(q("/a2a/import"), {
          method: "GET",
          headers: Se,
          signal: o.signal
        });
        if (!Ae.ok) {
          const Re = await Ae.text().catch(() => "");
          throw new Error(Re || `HTTP ${Ae.status}`);
        }
        const _e = await Ae.json(), We = (_e == null ? void 0 : _e.agents) || [];
        if (We.length === 0) {
          ne.warning("未找到可用的 Agent");
          return;
        }
        H(We);
        const Nt = y.current;
        V(
          new Set(
            We.filter((Re) => !Nt.has(Re.name)).map((Re) => Re.url)
          )
        );
      } catch (E) {
        if ((E == null ? void 0 : E.name) === "AbortError") return;
        ne.error(E.message || "获取 Agent 列表失败");
      } finally {
        f(!1), Z.current = null;
      }
    }, []), N = L((o) => {
      V((E) => {
        const S = new Set(E);
        return S.has(o) ? S.delete(o) : S.add(o), S;
      });
    }, []), we = L(() => {
      V(
        new Set(
          u.filter((o) => !$.has(o.name)).map((o) => o.url)
        )
      );
    }, [u, $]), M = L(() => {
      V(/* @__PURE__ */ new Set());
    }, []), j = L(async () => {
      const o = u.filter(
        (S) => oe.has(S.url) && !$.has(S.name)
      );
      if (o.length === 0) {
        ne.warning("请至少选择一个 Agent");
        return;
      }
      f(!0), me([]);
      const E = [];
      for (const S of o) {
        try {
          await Te(Ce, {
            method: "POST",
            body: JSON.stringify({
              url: S.url,
              alias: S.name || void 0,
              auth_type: S.auth_type || "gateway",
              auth_token: ""
            })
          }), E.push({ name: S.name || S.url, success: !0 });
        } catch (Se) {
          E.push({
            name: S.name || S.url,
            success: !1,
            error: Se.message || "注册失败"
          });
        }
        me([...E]);
      }
      await p(), ne.success(
        `导入完成：成功 ${E.filter((S) => S.success).length} 个，失败 ${E.filter((S) => !S.success).length} 个`
      ), f(!1), setTimeout(() => R(), 1500);
    }, [u, oe, p, $]), se = ((ct = de.useWatch) == null ? void 0 : ct.call(de, "auth_type", I)) ?? "", ae = e.createElement(
      de,
      { form: I, layout: "vertical" },
      e.createElement(
        de.Item,
        {
          name: "url",
          label: "Agent URL",
          rules: [{ required: !0, message: "请输入 Agent URL" }]
        },
        e.createElement(te, {
          placeholder: "https://agent.example.com"
        })
      ),
      e.createElement(
        de.Item,
        { name: "alias", label: "别名" },
        e.createElement(te, { placeholder: "输入别名（可选）" })
      ),
      e.createElement(
        de.Item,
        { name: "auth_type", label: "认证类型" },
        e.createElement(
          $e,
          { allowClear: !0, placeholder: "无认证" },
          e.createElement(
            $e.Option,
            { value: "bearer" },
            "Bearer Token"
          ),
          e.createElement($e.Option, { value: "api_key" }, "API Key"),
          e.createElement(
            $e.Option,
            { value: "gateway" },
            "阿里云Agent Hub"
          )
        )
      ),
      se === "gateway" ? e.createElement(
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
      se && se !== "gateway" ? e.createElement(
        de.Item,
        { name: "auth_token", label: "认证凭证" },
        e.createElement(te.Password, {
          placeholder: "Bearer Token 或 API Key"
        })
      ) : null
    ), ge = r ? e.createElement(
      "div",
      null,
      e.createElement(
        ie,
        { column: 1, bordered: !0, size: "small" },
        e.createElement(
          ie.Item,
          { label: "URL" },
          r.url
        ),
        e.createElement(
          ie.Item,
          { label: "别名" },
          r.alias || "-"
        ),
        e.createElement(
          ie.Item,
          { label: "Agent 名称" },
          r.name || "-"
        ),
        e.createElement(
          ie.Item,
          { label: "状态" },
          e.createElement(Ve, {
            color: r.status === "connected" ? "#52c41a" : r.status === "error" ? "#ff4d4f" : "#d9d9d9",
            text: r.status === "connected" ? "已连接" : r.status === "error" ? "错误" : "未连接"
          })
        ),
        e.createElement(
          ie.Item,
          { label: "认证类型" },
          r.auth_type ? e.createElement(
            D,
            { color: "blue" },
            {
              gateway: "阿里云Agent Hub",
              bearer: "Bearer Token",
              api_key: "API Key"
            }[r.auth_type] || r.auth_type
          ) : "无认证"
        ),
        e.createElement(
          ie.Item,
          { label: "描述" },
          r.description || "-"
        ),
        e.createElement(
          ie.Item,
          { label: "版本" },
          r.version || "-"
        )
      ),
      ((dt = r.skills) == null ? void 0 : dt.length) > 0 ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "技能"),
        ...r.skills.map(
          (o, E) => e.createElement(
            G,
            { key: E, size: "small", style: { marginBottom: 8 } },
            e.createElement("strong", null, o.name),
            o.description ? e.createElement(
              "div",
              { style: { color: "#666", fontSize: 12 } },
              o.description
            ) : null
          )
        )
      ) : null,
      r.capabilities ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "能力"),
        e.createElement(
          J,
          null,
          e.createElement(
            D,
            {
              color: r.capabilities.streaming ? "green" : "default"
            },
            "Streaming"
          ),
          e.createElement(
            D,
            {
              color: r.capabilities.push_notifications ? "green" : "default"
            },
            "Push Notifications"
          )
        )
      ) : null,
      r.error ? e.createElement(
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
        r.error
      ) : null,
      e.createElement(kt, null),
      e.createElement(
        J,
        null,
        e.createElement(
          b,
          {
            type: "primary",
            icon: Ne ? e.createElement(Ne) : null,
            loading: re,
            onClick: h
          },
          "刷新 Agent Card"
        ),
        e.createElement(
          b,
          {
            danger: !0,
            icon: tt ? e.createElement(tt) : null,
            onClick: m
          },
          "删除"
        )
      )
    ) : null, v = e.createElement(
      At,
      {
        title: z ? "注册远程 A2A Agent" : (r == null ? void 0 : r.name) || (r == null ? void 0 : r.alias) || "Agent 详情",
        open: d,
        onClose: T,
        width: 480,
        footer: z ? e.createElement(
          J,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(b, { onClick: T }, "取消"),
          e.createElement(
            b,
            { type: "primary", loading: B, onClick: k },
            "注册"
          )
        ) : null
      },
      z ? ae : ge
    ), ee = e.createElement(
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
          J,
          null,
          e.createElement(
            b,
            {
              icon: Ne ? e.createElement(Ne) : null,
              onClick: p,
              loading: i
            },
            "刷新列表"
          ),
          e.createElement(
            b,
            {
              icon: Ze ? e.createElement(Ze) : null,
              onClick: x
            },
            "从阿里云AgentHub导入"
          ),
          e.createElement(
            b,
            {
              type: "primary",
              icon: et ? e.createElement(et) : null,
              onClick: _
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
    ), De = i ? e.createElement(
      "div",
      { style: { textAlign: "center", padding: 60 } },
      e.createElement(ye, { size: "large" })
    ) : n.length === 0 ? e.createElement(bt, {
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
      ...n.map(
        (o) => e.createElement(Ct, {
          key: o.alias || o.url,
          agent: o,
          onClick: () => g(o)
        })
      )
    ), Ee = xe.length > 0, Ie = Math.ceil(u.length / pe), it = (ue - 1) * pe, Ot = u.slice(it, it + pe), $t = e.createElement(
      Qe,
      {
        title: Ee ? "导入结果" : "从阿里云AgentHub导入 Agent",
        open: Q,
        onCancel: R,
        closable: !c || Ee,
        maskClosable: !c || Ee,
        width: 800,
        footer: Ee ? e.createElement(
          J,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            b,
            { type: "primary", onClick: R },
            "关闭"
          )
        ) : u.length > 0 ? e.createElement(
          J,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            b,
            { onClick: R },
            "取消"
          ),
          e.createElement(
            b,
            {
              type: "primary",
              loading: c,
              disabled: oe.size === 0,
              onClick: j
            },
            `确认导入 (${oe.size}/${u.length})`
          )
        ) : null
      },
      // Loading state
      c && u.length === 0 && e.createElement(
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
          { style: { fontSize: 13, color: "#8c8c8c" } },
          "正在从 AgentHub 获取 Agent 列表..."
        )
      ),
      // Agent selection list
      !c && u.length > 0 && e.createElement(
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
              color: "#8c8c8c"
            }
          },
          e.createElement(
            "span",
            null,
            `共 ${u.length} 个 Agent，已选 ${oe.size} 个`
          ),
          e.createElement(
            J,
            { size: 4 },
            e.createElement(
              b,
              {
                size: "small",
                type: "link",
                style: { padding: 0, height: "auto" },
                onClick: we
              },
              "全选"
            ),
            e.createElement(
              b,
              {
                size: "small",
                type: "link",
                style: { padding: 0, height: "auto" },
                onClick: M
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
          ...Ot.map((o, E) => {
            var Se;
            const S = oe.has(o.url);
            return e.createElement(
              "div",
              {
                key: E,
                style: {
                  display: "flex",
                  gap: 8,
                  padding: 10,
                  border: S ? "1px solid #1677ff" : "1px solid #e8e8e8",
                  borderRadius: 6,
                  cursor: $.has(o.name) ? "default" : "pointer",
                  background: $.has(o.name) ? "#fafafa" : S ? "#f6f9ff" : "#fff",
                  transition: "all 0.15s ease",
                  opacity: $.has(o.name) ? 0.7 : 1
                },
                onClick: () => {
                  $.has(o.name) || N(o.url);
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
                  o.name || o.url
                ),
                o.description ? e.createElement(
                  "div",
                  {
                    style: {
                      fontSize: 11,
                      color: "#8c8c8c",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap"
                    }
                  },
                  o.description
                ) : null,
                ((Se = o.skills) == null ? void 0 : Se.length) > 0 ? e.createElement(
                  "div",
                  { style: { marginTop: 4 } },
                  ...o.skills.slice(0, 3).map(
                    (Ae, _e) => e.createElement(
                      D,
                      {
                        key: _e,
                        style: {
                          fontSize: 10,
                          marginRight: 4
                        }
                      },
                      Ae.name
                    )
                  ),
                  o.skills.length > 3 ? e.createElement(
                    D,
                    { style: { fontSize: 10 } },
                    `+${o.skills.length - 3}`
                  ) : null
                ) : null
              ),
              e.createElement(
                D,
                {
                  color: $.has(o.name) ? "green" : "blue",
                  style: { fontSize: 10, flexShrink: 0, height: 20 }
                },
                $.has(o.name) ? "已导入" : o.auth_type === "gateway" ? "阿里云" : o.auth_type
              )
            );
          })
        ),
        // Pagination
        Ie > 1 && e.createElement(
          "div",
          {
            style: {
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              gap: 8,
              marginTop: 16
            }
          },
          e.createElement(
            b,
            {
              size: "small",
              disabled: ue === 1,
              onClick: () => fe((o) => o - 1)
            },
            "上一页"
          ),
          e.createElement(
            "span",
            { style: { fontSize: 12, color: "#8c8c8c" } },
            `${ue} / ${Ie}`
          ),
          e.createElement(
            b,
            {
              size: "small",
              disabled: ue === Ie,
              onClick: () => fe((o) => o + 1)
            },
            "下一页"
          )
        )
      ),
      // Import results
      Ee && e.createElement(
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
        ...xe.map(
          (o, E) => e.createElement(
            "div",
            {
              key: E,
              style: {
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                borderRadius: 4,
                background: o.success ? "#f6ffed" : "#fff2f0",
                border: o.success ? "1px solid #b7eb8f" : "1px solid #ffccc7",
                fontSize: 12
              }
            },
            e.createElement(
              "span",
              {
                style: {
                  color: o.success ? "#52c41a" : "#ff4d4f",
                  fontSize: 14
                }
              },
              o.success ? "✓" : "✗"
            ),
            e.createElement(
              "span",
              {
                style: {
                  flex: 1,
                  color: o.success ? "#262626" : "#ff4d4f"
                }
              },
              o.name,
              o.error ? ` - ${o.error}` : ""
            )
          )
        )
      )
    );
    return e.createElement(
      "div",
      { style: { padding: 24 } },
      ee,
      De,
      v,
      $t
    );
  }
  function It({ data: t }) {
    var Z, pe, $;
    const n = e.useRef(null), [l, i] = C({}), a = he(() => {
      var p, _, g;
      const y = (g = (_ = (p = t == null ? void 0 : t.content) == null ? void 0 : p[0]) == null ? void 0 : _.data) == null ? void 0 : g.arguments;
      if (!y) return null;
      try {
        return JSON.parse(y);
      } catch {
        return null;
      }
    }, [($ = (pe = (Z = t == null ? void 0 : t.content) == null ? void 0 : Z[0]) == null ? void 0 : pe.data) == null ? void 0 : $.arguments]), { toolResult: d, rawErrorText: s } = he(() => {
      var p;
      const y = t == null ? void 0 : t.content;
      if (!Array.isArray(y))
        return { toolResult: null, rawErrorText: "" };
      for (const _ of y) {
        const g = (p = _ == null ? void 0 : _.data) == null ? void 0 : p.output;
        if (!g) continue;
        let T = "";
        if (Array.isArray(g)) {
          const k = g.find(
            (m) => (m == null ? void 0 : m.type) === "text" && (m == null ? void 0 : m.text)
          );
          T = (k == null ? void 0 : k.text) || "";
        } else if (typeof g == "string")
          try {
            const k = JSON.parse(g);
            if (typeof k == "object" && (k != null && k.steps || k != null && k.response_text))
              return { toolResult: k, rawErrorText: "" };
            if (Array.isArray(k)) {
              const m = k.find((h) => (h == null ? void 0 : h.type) === "text" && (h == null ? void 0 : h.text));
              m != null && m.text && (T = m.text);
            }
          } catch {
            T = g;
          }
        if (T)
          try {
            return { toolResult: JSON.parse(T), rawErrorText: "" };
          } catch {
            return { toolResult: null, rawErrorText: T };
          }
      }
      return { toolResult: null, rawErrorText: "" };
    }, [t == null ? void 0 : t.content]), r = (d == null ? void 0 : d.steps) || [], w = (d == null ? void 0 : d.task_state) || "", z = (d == null ? void 0 : d.error) || "", A = (d == null ? void 0 : d.response_text) || "";
    e.useEffect(() => {
      n.current && (n.current.scrollTop = n.current.scrollHeight);
    }, [r.length, A, s]), e.useEffect(() => {
      const y = { ...l };
      let p = !1;
      r.forEach((_, g) => {
        l[g] === void 0 && (_.type === "thinking" && _.done || _.type === "tool_call" && _.status !== "running") && (y[g] = !0, p = !0);
      }), p && i(y);
    }, [r]);
    const B = (a == null ? void 0 : a.agent_alias) || "", K = (a == null ? void 0 : a.agent_url) || "", re = B || K || "远程 Agent", P = {
      completed: { color: "#52c41a", text: "已完成" },
      TASK_STATE_COMPLETED: { color: "#52c41a", text: "已完成" },
      failed: { color: "#ff4d4f", text: "失败" },
      TASK_STATE_FAILED: { color: "#ff4d4f", text: "失败" },
      error: { color: "#ff4d4f", text: "出错" },
      canceled: { color: "#faad14", text: "已取消" },
      TASK_STATE_CANCELED: { color: "#faad14", text: "已取消" },
      AWAITING_USER_INPUT: { color: "#1677ff", text: "等待输入" },
      input_required: { color: "#1677ff", text: "等待输入" }
    }, O = (d !== null || !!s) && !(w === "working" || w === "TASK_STATE_WORKING");
    let c = "#1677ff", f = "执行中...";
    O && (P[w] ? (c = P[w].color, f = P[w].text) : s ? (c = "#ff4d4f", f = "出错") : (c = "#52c41a", f = "已完成"));
    const u = e.createElement(
      J,
      { size: 6 },
      e.createElement("span", { style: { fontSize: 13 } }, "🔗"),
      e.createElement(
        X,
        { style: { fontSize: 12, color: "#595959" } },
        `A2A: ${re}`
      ),
      e.createElement(
        D,
        { color: c, style: { fontSize: 11, lineHeight: "18px" } },
        f
      )
    ), H = r.length === 0 && !s && !z, oe = !O && H ? e.createElement(
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
        X,
        { style: { fontSize: 12, color: "#52c41a" } },
        `正在连接 ${re}...`
      )
    ) : null;
    function V(y) {
      i((p) => ({
        ...p,
        [y]: !p[y]
      }));
    }
    function xe(y, p) {
      const _ = !!l[p];
      if (y.type === "thinking") {
        const g = !!y.done, T = g ? "💭" : "🧠", k = g ? "思考完成" : "思考中...", m = e.createElement(
          "div",
          {
            key: `step-${p}`,
            style: {
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: g ? "pointer" : "default",
              fontSize: 12,
              color: "#8c8c8c"
            },
            onClick: g ? () => V(p) : void 0
          },
          g && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            _ ? "▶" : "▼"
          ),
          e.createElement("span", null, T),
          e.createElement("span", null, k),
          !g && e.createElement(ye, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return _ ? m : e.createElement(
          "div",
          { key: `step-${p}` },
          m,
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
            y.text || ""
          )
        );
      }
      if (y.type === "tool_call") {
        const g = y.status === "running", T = y.status === "error", k = g ? "⚙️" : T ? "❌" : "✅", m = g ? `正在执行: ${y.name}` : T ? `执行失败: ${y.name}` : `执行完成: ${y.name}`, h = g ? "#1677ff" : T ? "#ff4d4f" : "#52c41a", x = e.createElement(
          "div",
          {
            key: `step-${p}`,
            style: {
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: g ? "default" : "pointer",
              fontSize: 12,
              color: h
            },
            onClick: g ? void 0 : () => V(p)
          },
          !g && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            _ ? "▶" : "▼"
          ),
          e.createElement("span", null, k),
          e.createElement("span", null, m),
          g && e.createElement(ye, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return _ || !y.desc && !g ? x : e.createElement(
          "div",
          { key: `step-${p}` },
          x,
          y.desc && e.createElement(
            "div",
            {
              style: {
                marginLeft: 20,
                padding: "2px 8px",
                fontSize: 11,
                color: "#8c8c8c"
              }
            },
            y.desc
          )
        );
      }
      return y.type === "text" ? e.createElement(
        "div",
        {
          key: `step-${p}`,
          style: {
            padding: "4px 0",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: "1.6",
            color: "#262626"
          }
        },
        y.text || ""
      ) : null;
    }
    const me = r.length > 0 ? e.createElement(
      "div",
      {
        ref: n,
        style: {
          background: "#fafafa",
          border: "1px solid #e8e8e8",
          borderRadius: 6,
          padding: "6px 10px",
          maxHeight: 200,
          overflowY: "auto"
        }
      },
      ...r.map(xe)
    ) : null, ue = s || z ? e.createElement(
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
      z ? `错误: ${z}` : s
    ) : null, fe = !r.length && A && !s ? e.createElement(
      "div",
      {
        ref: n,
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
        X,
        {
          style: {
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: "1.6"
          }
        },
        A
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
      e.createElement("div", { style: { marginBottom: 6 } }, u),
      oe,
      me,
      fe,
      ue
    );
  }
  const _t = "__A2A_STREAM_START__", Rt = "A2A_STREAM_START", ve = /* @__PURE__ */ new Set();
  function Be(t) {
    return t ? t.includes(_t) || t.includes(Rt) : !1;
  }
  function He(t) {
    var n, l;
    return t.getAttribute("data-msg-id") || t.getAttribute("data-message-id") || ((n = t.closest("[data-msg-id]")) == null ? void 0 : n.getAttribute("data-msg-id")) || ((l = t.closest("[data-message-id]")) == null ? void 0 : l.getAttribute("data-message-id")) || null;
  }
  function zt(t) {
    if (Be(t.innerHTML) || Be(t.textContent))
      return t;
    const n = document.createTreeWalker(
      t,
      NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT
    );
    for (; n.nextNode(); ) {
      const l = n.currentNode, i = l.nodeType === Node.TEXT_NODE ? l.textContent : l.innerHTML;
      if (Be(i)) {
        const a = l.nodeType === Node.TEXT_NODE ? l.parentElement : l;
        if (a) return a;
      }
    }
    return null;
  }
  async function je(t) {
    var w, z;
    const n = window.QwenPaw;
    if (!(n != null && n.host)) {
      console.warn("[a2a] QwenPaw.host not available");
      return;
    }
    const { getApiUrl: l, getApiToken: i } = n.host, a = l("/a2a/call/stream"), d = i();
    console.log("[a2a] Subscribing to SSE stream:", a);
    const s = document.createElement("div");
    s.style.cssText = "background:#f6ffed;border:1px solid #b7eb8f;border-radius:8px;padding:12px 16px;margin:4px 0;font-size:13px;white-space:pre-wrap;word-break:break-word;color:#262626;min-height:24px;", s.textContent = "正在连接远程 Agent...", t.textContent = "", t.appendChild(s);
    const r = new AbortController();
    try {
      const A = {
        Accept: "text/event-stream"
      };
      d && (A.Authorization = `Bearer ${d}`);
      try {
        const I = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage"), Q = (z = (w = JSON.parse(I || "{}")) == null ? void 0 : w.state) == null ? void 0 : z.selectedAgent;
        Q && (A["X-Agent-Id"] = Q);
      } catch {
      }
      console.log("[a2a] Fetching SSE with headers:", A);
      const B = await fetch(a, { headers: A, signal: r.signal });
      if (console.log("[a2a] SSE response status:", B.status), !B.ok) {
        const I = await B.text().catch(() => "");
        s.textContent = `SSE 连接失败 (${B.status}): ${I.slice(
          0,
          100
        )}`, s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0";
        return;
      }
      if (!B.body) {
        s.textContent = "SSE 连接失败：无响应体", s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0";
        return;
      }
      const K = B.body.getReader(), re = new TextDecoder();
      let P = "";
      for (; ; ) {
        const { done: I, value: Q } = await K.read();
        if (I) {
          console.log("[a2a] SSE stream ended (done)");
          break;
        }
        P += re.decode(Q, { stream: !0 });
        const O = P.split(`
`);
        P = O.pop() || "";
        for (const c of O)
          if (c.startsWith("data: "))
            try {
              const f = JSON.parse(c.slice(6));
              if (console.log("[a2a] SSE event:", f), f.done) {
                f.error && (s.textContent = `错误: ${f.error}`, s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0"), console.log("[a2a] SSE done signal received");
                return;
              }
              typeof f.response_text == "string" && f.response_text && (s.textContent = f.response_text);
            } catch (f) {
              console.warn("[a2a] SSE parse error:", f, "line:", c);
            }
      }
    } catch (A) {
      (A == null ? void 0 : A.name) !== "AbortError" && (console.error("[a2a] SSE subscription error:", A), s.textContent = `连接出错: ${(A == null ? void 0 : A.message) || A}`, s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0");
    }
  }
  function Pt() {
    console.log("[a2a] Initializing stream interceptor");
    function t(a) {
      if (a.nodeType !== Node.ELEMENT_NODE) return;
      const d = a, s = He(d);
      if (s && ve.has(s)) return;
      const r = zt(d);
      r && (console.log("[a2a] Marker detected in DOM, msgId:", s), s && ve.add(s), je(r));
    }
    new MutationObserver((a) => {
      for (const d of a) {
        for (const s of d.addedNodes)
          t(s);
        d.target.nodeType === Node.ELEMENT_NODE && t(d.target);
      }
    }).observe(document.body, {
      childList: !0,
      subtree: !0,
      characterData: !0,
      characterDataOldValue: !0
    });
    const l = setInterval(() => {
      const a = document.evaluate(
        "//text()[contains(., 'A2A_STREAM_START')]",
        document.body,
        null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
        null
      );
      for (let d = 0; d < a.snapshotLength; d++) {
        const r = a.snapshotItem(d).parentElement;
        if (r) {
          const w = He(r);
          if (w && ve.has(w)) continue;
          console.log("[a2a] Marker found in periodic scan, msgId:", w), w && ve.add(w), je(r);
        }
      }
    }, 500);
    window.addEventListener("beforeunload", () => clearInterval(l));
    const i = document.evaluate(
      "//text()[contains(., 'A2A_STREAM_START')]",
      document.body,
      null,
      XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
      null
    );
    for (let a = 0; a < i.snapshotLength; a++) {
      const s = i.snapshotItem(a).parentElement;
      if (s) {
        const r = He(s);
        r && ve.add(r), console.log("[a2a] Marker found in existing DOM, msgId:", r), je(s);
      }
    }
  }
  (lt = (ot = window.QwenPaw).registerToolRender) == null || lt.call(ot, "cloudpaw", {
    proposal_choice: wt,
    manage_prd: St,
    a2a_call: It
  }), (at = (st = window.QwenPaw).registerRoutes) == null || at.call(st, "cloudpaw", [
    {
      path: "/a2a",
      component: vt,
      label: "A2A",
      icon: "🔗",
      priority: 10
    }
  ]), Dt(), Lt(), Pt();
}
function Dt() {
  const e = "qwenpaw-last-used-agent", F = "qwenpaw-agent-storage", Y = "cloudpaw-first-install", q = "cloud-orchestrator";
  if (localStorage.getItem(Y)) return;
  localStorage.setItem(Y, "true");
  function U() {
    localStorage.setItem(e, q);
    try {
      const G = localStorage.getItem(F);
      if (G) {
        const W = JSON.parse(G);
        W.state = W.state || {}, W.state.selectedAgent = q, localStorage.setItem(F, JSON.stringify(W));
      } else
        localStorage.setItem(
          F,
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
      const G = sessionStorage.getItem(F);
      if (G) {
        const W = JSON.parse(G);
        W.state = W.state || {}, W.state.selectedAgent = q, sessionStorage.setItem(F, JSON.stringify(W));
      } else
        sessionStorage.setItem(
          F,
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
function Lt() {
  var J;
  const e = (J = window.QwenPaw) == null ? void 0 : J.modules;
  if (!e) return;
  const F = e["Chat/OptionsPanel/defaultConfig"];
  if (!(F != null && F.configProvider)) {
    console.warn(
      "[cloudpaw] configProvider not found — skipping welcome/theme patch"
    );
    return;
  }
  const Y = F.configProvider, q = Y.getConfig.bind(Y), U = "https://gw.alicdn.com/imgextra/i2/O1CN01pyXzjQ1EL1PuZMlSd_!!6000000000334-2-tps-288-288.png", G = {
    zh: "CloudPaw 插件提示",
    en: "CloudPaw Plugin Tips",
    ja: "CloudPaw プラグインのヒント",
    ru: "Подсказки плагина CloudPaw"
  }, W = {
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
  }, D = {
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
  function be() {
    const b = localStorage.getItem("language") || "";
    return b ? b.split("-")[0] : (navigator.language || "").split("-")[0] || "en";
  }
  if (Y.getGreeting = () => G[be()] || G.en, Y.getDescription = () => W[be()] || W.en, Y.getPrompts = () => D[be()] || D.en, Y.getConfig = function(b) {
    var ke;
    const te = q(b);
    return {
      ...te,
      theme: {
        ...te.theme,
        leftHeader: {
          ...(ke = te.theme) == null ? void 0 : ke.leftHeader,
          title: "Work with CloudPaw"
        }
      },
      welcome: {
        ...te.welcome,
        avatar: U
      }
    };
  }, !document.getElementById("cloudpaw-welcome-style")) {
    const b = document.createElement("style");
    b.id = "cloudpaw-welcome-style", b.textContent = `
      [class*="chat-anywhere-welcome-default"] [class*="description"],
      [class*="message-list-welcome"] [class*="description"] {
        white-space: pre-line !important;
        text-align: center !important;
      }
    `, document.head.appendChild(b);
  }
  console.info("[cloudpaw] Patched welcome config & theme via configProvider");
}
Mt();
