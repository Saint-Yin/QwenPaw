function Dt() {
  var st, at, it, ct;
  const { React: e, antd: F, antdIcons: Y, getApiUrl: q, getApiToken: K } = window.QwenPaw.host, {
    Card: G,
    Table: W,
    Tag: M,
    Typography: ke,
    Space: J,
    Button: b,
    Input: ne,
    Radio: Te,
    Descriptions: ce,
    Tooltip: Ue,
    Spin: he,
    message: Ke,
    theme: $e
  } = F, { Text: X } = ke, { TextArea: ft } = ne, { useState: T, useMemo: Ee, useCallback: D } = e, {
    InfoCircleOutlined: Pe,
    DownOutlined: Ye,
    RightOutlined: pt,
    CheckCircleOutlined: Oe,
    FieldTimeOutlined: Be,
    FileTextOutlined: qe
  } = Y || {};
  function Ge(t) {
    var i, c;
    const n = (c = (i = t == null ? void 0 : t.content) == null ? void 0 : i[0]) == null ? void 0 : c.data, r = n == null ? void 0 : n.arguments;
    if (typeof r == "string")
      try {
        return JSON.parse(r);
      } catch {
        return {};
      }
    return r ?? {};
  }
  function gt() {
    return window.currentSessionId ?? null;
  }
  function de(t) {
    return typeof t == "string" ? t : t && typeof t == "object" && "text" in t ? t.text : String(t ?? "");
  }
  function yt(t) {
    if (t == null) return !0;
    const n = de(t).trim();
    return !!(!n || /^[¥$]?0+(\.0+)?$/.test(n) || /^[-–—]+$/.test(n));
  }
  async function ht(t, n) {
    try {
      const r = K(), i = {
        "Content-Type": "application/json"
      };
      return r && (i.Authorization = `Bearer ${r}`), (await fetch(q("/interaction"), {
        method: "POST",
        headers: i,
        body: JSON.stringify({ session_id: t, result: n })
      })).ok;
    } catch {
      return !1;
    }
  }
  function Xe(t) {
    if (!t) return null;
    if (typeof t == "string")
      try {
        const n = JSON.parse(t);
        if (Array.isArray(n)) {
          const r = n.find(
            (i) => (i == null ? void 0 : i.type) === "text" && (i == null ? void 0 : i.text)
          );
          return (r == null ? void 0 : r.text) ?? null;
        }
        if (typeof n == "string") return n;
      } catch {
        return t;
      }
    if (Array.isArray(t)) {
      const n = t.find((r) => (r == null ? void 0 : r.type) === "text" && (r == null ? void 0 : r.text));
      return (n == null ? void 0 : n.text) ?? null;
    }
    return null;
  }
  function Et(t) {
    var s, m;
    if (!t || t.length < 2) return null;
    const n = (m = (s = t[1]) == null ? void 0 : s.data) == null ? void 0 : m.output, r = Xe(n);
    if (!r) return null;
    if (r.startsWith("Error:")) return r;
    const i = r.match(/^用户选择了「(.+?)」并确认部署$/);
    if (i) return `已确认部署「${i[1]}」`;
    const c = r.match(
      /^用户选择「(.+?)」并要求调整[：:](.+)$/
    );
    if (c)
      return `已选择「${c[1]}」并调整：${c[2]}`;
    if (r === "用户确认部署") return "已确认部署";
    const d = r.match(/^用户要求调整资源[：:](.+)$/);
    return d ? `已反馈调整意见：${d[1]}` : "已确认";
  }
  const Qe = [
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
  ], xt = new Set(
    Qe.map((t) => t.toLowerCase())
  );
  function He(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = de(t[0]).trim().toLowerCase();
    return xt.has(n);
  }
  function Ve(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = de(t[0]).trim();
    return /^(合计|总计|total)/i.test(n);
  }
  function St(t) {
    const n = [];
    let r = [];
    for (const i of t)
      r.push(i), Ve(i) && (n.push(r), r = []);
    return r.length > 0 && (n.length > 0 ? n[n.length - 1].push(...r) : n.push(r)), n.length > 0 ? n : [t];
  }
  function wt(t) {
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
  function At({ data: t }) {
    var g, C, k;
    const { token: n } = $e.useToken(), [r, i] = T("confirm"), [c, d] = T(""), [s, m] = T(!1), [l, I] = T(null), [w, O] = T(
      {}
    ), V = e.useRef(!1), U = e.useRef(null), [, Q] = T(0), _ = t == null ? void 0 : t.content, $ = _ && _.length >= 2 && ((C = (g = _[1]) == null ? void 0 : g.data) == null ? void 0 : C.output), oe = Ee(
      () => Et(_),
      [_]
    ), P = V.current || $ || oe !== null, a = Ee(() => {
      const f = Ge(t), h = f == null ? void 0 : f.data;
      if (!h) return null;
      try {
        const x = typeof h == "string" ? JSON.parse(h) : h;
        let z;
        if (f.strategy_names)
          try {
            const N = typeof f.strategy_names == "string" ? JSON.parse(f.strategy_names) : f.strategy_names;
            z = Array.isArray(N) ? N : [];
          } catch {
            z = [];
          }
        else x != null && x.proposal_names ? z = x.proposal_names : z = [];
        const se = z.length >= 2 ? z.length : 0;
        let B;
        if (Array.isArray(x) && x.length > 0)
          if (Array.isArray(x[0]) && x[0].length === 10 && !Array.isArray(x[0][0])) {
            const j = x.filter(
              (ie) => !He(ie)
            );
            if (j.filter(
              (ie) => Ve(ie)
            ).length >= 2)
              B = St(j);
            else if (se >= 2 && j.length >= se * 2) {
              const ie = Math.ceil(j.length / se);
              B = [];
              for (let ye = 0; ye < j.length; ye += ie)
                B.push(j.slice(ye, ye + ie));
            } else
              B = [j];
          } else
            B = x.map(
              (j) => j.filter(
                (ae) => Array.isArray(ae) && ae.length === 10 && !He(ae)
              )
            );
        else if (x != null && x.proposals)
          B = x.proposals.map(
            (N) => N.filter((j) => !He(j))
          );
        else
          return null;
        if (B = B.filter((N) => N.length > 0), B.length === 0) return null;
        const we = ["方案一", "方案二", "方案三", "方案四", "方案五"];
        if (z.length < B.length)
          for (let N = z.length; N < B.length; N++)
            z.push(we[N] || `方案${N + 1}`);
        return { proposals: B, names: z };
      } catch {
        return null;
      }
    }, [t]), S = gt(), u = (((k = a == null ? void 0 : a.proposals) == null ? void 0 : k.length) ?? 0) > 1, L = D(async () => {
      if (!S || P || !a) return;
      const f = u ? l : 0, h = a.names[f ?? 0] || `方案${(f ?? 0) + 1}`;
      let x;
      r === "confirm" ? x = `用户选择了「${h}」并确认部署` : x = `用户选择「${h}」并要求调整：${c.trim() || "未填写具体要求"}`, m(!0);
      const z = await ht(S, x);
      m(!1), z ? (V.current = !0, r === "confirm" ? U.current = `已确认部署「${h}」` : U.current = `已选择「${h}」并调整：${c.trim()}`, Q((se) => se + 1), Ke.success(
        r === "confirm" ? "已确认部署方案" : "已提交调整意见"
      )) : Ke.error("操作失败，请重试");
    }, [
      S,
      P,
      a,
      r,
      c,
      l,
      u
    ]), le = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created";
    if (!a)
      return le ? e.createElement(
        "div",
        {
          style: {
            width: "100%",
            borderRadius: 10,
            border: `1px solid ${n.colorBorderSecondary}`,
            background: n.colorBgContainer,
            padding: "24px 16px",
            margin: "4px 0",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12
          }
        },
        e.createElement(he, { size: "default" }),
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
    const { proposals: Z, names: Se } = a, pe = Qe.map((f, h) => ({
      title: f,
      dataIndex: `col_${h}`,
      key: `col_${h}`,
      render: (x) => wt(x),
      ellipsis: h < 3
    }));
    let me = "待确认", fe = "processing";
    P && (fe = "success", me = U.current || oe || "已确认");
    const ee = e.createElement(
      M,
      {
        color: fe,
        style: { marginLeft: 4 }
      },
      me
    ), ge = e.createElement(
      J,
      { size: 8 },
      e.createElement("span", null, "☁️"),
      e.createElement(
        X,
        { strong: !0, style: { fontSize: 14 } },
        P ? "资源配置方案" : "请确认您的资源配置方案"
      ),
      ee
    ), H = Z.map((f, h) => {
      const x = u ? l === h : !0, z = w[h] || !1, se = (v) => {
        const te = de(v[0] || "").trim();
        return /^合计|^总计|^total/i.test(te);
      }, B = f.find(se), we = f.filter((v) => !se(v)), N = we.map((v) => ({
        type: de(v[0] || ""),
        purpose: de(v[1] || ""),
        spec: de(v[2] || ""),
        cost: v[9] ?? null
      })), j = B ? de(B[9] ?? "") : "", ae = f.map((v, te) => {
        const Le = { key: te };
        return v.forEach((xe, _e) => {
          Le[`col_${_e}`] = xe;
        }), Le;
      }), ie = x ? `2px solid ${n.colorInfo}` : `1px solid ${n.colorBorderSecondary}`, ye = x ? `0 0 0 2px ${n.colorInfoBg}` : "none";
      return e.createElement(
        "div",
        {
          key: h,
          style: {
            flex: 1,
            minWidth: 240,
            border: ie,
            borderRadius: 8,
            cursor: u ? "pointer" : "default",
            transition: "all 0.2s ease",
            boxShadow: ye,
            background: n.colorBgContainer
          },
          onClick: u ? () => I(h) : void 0
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
            Se[h]
          ),
          ...N.map(
            (v, te) => e.createElement(
              "div",
              {
                key: te,
                style: {
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "4px 0",
                  borderBottom: te < N.length - 1 ? `1px solid ${n.colorSplit}` : "none"
                }
              },
              e.createElement(
                "div",
                { style: { flex: 1, minWidth: 0 } },
                e.createElement(
                  "span",
                  { style: { fontSize: 12, color: n.colorText } },
                  v.type
                ),
                v.spec && e.createElement(
                  "span",
                  {
                    style: {
                      fontSize: 11,
                      color: n.colorTextTertiary,
                      marginLeft: 6
                    }
                  },
                  v.spec
                )
              ),
              !yt(v.cost) && e.createElement(
                "span",
                {
                  style: {
                    fontSize: 12,
                    color: n.colorTextSecondary,
                    flexShrink: 0,
                    marginLeft: 8
                  }
                },
                de(v.cost)
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
                borderTop: `1px dashed ${n.colorBorder}`
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
                color: n.colorTextTertiary,
                fontSize: 12,
                cursor: "pointer",
                marginTop: 6
              },
              onClick: (v) => {
                v.stopPropagation(), O((te) => ({
                  ...te,
                  [h]: !te[h]
                }));
              }
            },
            e.createElement(
              z && Ye ? Ye : pt || "span",
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
          z && e.createElement(
            "div",
            {
              onClick: (v) => v.stopPropagation(),
              style: { marginTop: 4, maxHeight: 260, overflow: "auto" }
            },
            e.createElement(W, {
              columns: pe,
              dataSource: ae,
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
          background: n.colorWarningBg,
          border: `1px solid ${n.colorWarningBorder}`,
          borderRadius: 6,
          padding: "8px 12px",
          marginBottom: 10,
          display: "flex",
          alignItems: "flex-start",
          gap: 8
        }
      },
      Pe ? e.createElement(Pe, {
        style: {
          color: n.colorWarning,
          fontSize: 14,
          flexShrink: 0,
          marginTop: 1
        }
      }) : e.createElement("span", null, "⚠️"),
      e.createElement(
        "span",
        {
          style: {
            fontSize: 12,
            color: n.colorWarningText,
            lineHeight: 1.5
          }
        },
        "在服务部署与配置过程中，可能因实际资源需求变化导致资源变配及费用调整，请及时关注实际资源使用情况与账单详情。"
      )
    ), p = !P && S && !(u && l === null) && e.createElement(
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
              border: `1px solid ${r === "confirm" ? n.colorInfo : n.colorBorder}`,
              borderRadius: 6,
              padding: "8px 12px",
              cursor: "pointer",
              transition: "all 0.15s ease",
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: r === "confirm" ? n.colorInfoBg : "transparent"
            },
            onClick: () => i("confirm")
          },
          e.createElement(Te, { checked: r === "confirm" }),
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
              border: `1px solid ${r === "adjust" ? n.colorInfo : n.colorBorder}`,
              borderRadius: 6,
              padding: "8px 12px",
              transition: "all 0.15s ease",
              background: r === "adjust" ? n.colorInfoBg : "transparent"
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
              onClick: () => i("adjust")
            },
            e.createElement(Te, { checked: r === "adjust" }),
            e.createElement(
              "span",
              { style: { fontSize: 13 } },
              "调整资源"
            )
          ),
          r === "adjust" && e.createElement(ft, {
            value: c,
            onChange: (f) => d(f.target.value),
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
            loading: s,
            onClick: L,
            disabled: r === "adjust" && !c.trim()
          },
          r === "confirm" ? "确认部署" : "提交调整"
        )
      )
    ), R = u && l === null && !P && e.createElement(
      "div",
      {
        style: {
          textAlign: "center",
          padding: "8px 0 4px",
          color: n.colorTextQuaternary,
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
          border: `1px solid ${n.colorBorder}`,
          overflow: "hidden",
          background: n.colorBgContainer,
          padding: "12px 16px",
          margin: "4px 0"
        }
      },
      // Header
      e.createElement("div", { style: { marginBottom: 10 } }, ge),
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
        ...H
      ),
      R,
      y,
      !P && p
    );
  }
  function bt({ data: t }) {
    const { token: n } = $e.useToken(), [r, i] = T(null), [c, d] = T(!1), s = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created", m = Ee(() => {
      const a = Ge(t);
      return (a == null ? void 0 : a.loop_dir) || null;
    }, [t]), l = Ee(() => {
      var S, u, L;
      const a = Xe((L = (u = (S = t == null ? void 0 : t.content) == null ? void 0 : S[1]) == null ? void 0 : u.data) == null ? void 0 : L.output);
      if (!a) return null;
      try {
        return JSON.parse(a);
      } catch {
        return null;
      }
    }, [t]), I = (l == null ? void 0 : l.status) === "ok", w = (l == null ? void 0 : l.status) === "error", O = w ? (l == null ? void 0 : l.message) || "未知错误" : null, V = D(async () => {
      if (m)
        try {
          const a = K(), S = {};
          a && (S.Authorization = `Bearer ${a}`);
          const u = await fetch(
            q(`/prd?loop_dir=${encodeURIComponent(m)}`),
            { headers: S }
          );
          if (!u.ok) {
            d(!0);
            return;
          }
          const L = await u.json();
          L && Array.isArray(L.userStories) ? (i(L), d(!1)) : d(!0);
        } catch {
          d(!0);
        }
    }, [m]);
    if (e.useEffect(() => {
      !s && I && m && V();
    }, [s, I, m, V]), s)
      return e.createElement(
        "div",
        {
          style: {
            width: "100%",
            borderRadius: 10,
            border: `1px solid ${n.colorBorderSecondary}`,
            background: n.colorBgContainer,
            padding: "24px 16px",
            margin: "4px 0",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12
          }
        },
        e.createElement(he, { size: "default" }),
        e.createElement(
          X,
          { type: "secondary", style: { fontSize: 13 } },
          "正在更新 PRD..."
        )
      );
    if (w)
      return e.createElement(
        "div",
        {
          style: {
            width: "100%",
            borderRadius: 10,
            border: `1px solid ${n.colorErrorBorder}`,
            background: n.colorErrorBg,
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
          `PRD 格式错误，将会修正：${O}`
        )
      );
    if (!I || c || !r) return null;
    const U = r.userStories, Q = [...U].sort(
      (a, S) => (a.priority || 99) - (S.priority || 99)
    ), _ = U.filter((a) => a.passes).length, $ = [
      {
        title: "状态",
        key: "status",
        width: 50,
        align: "center",
        render: (a, S) => {
          if (S.passes) {
            const L = Oe ? e.createElement(Oe, {
              style: { color: "#52c41a", fontSize: 18 }
            }) : "✅";
            return e.createElement(Ue, { title: "已完成" }, L);
          }
          const u = Be ? e.createElement(Be, {
            style: { color: "#faad14", fontSize: 18 }
          }) : "🕐";
          return e.createElement(Ue, { title: "待处理" }, u);
        }
      },
      {
        title: "ID",
        dataIndex: "id",
        key: "id",
        width: 85,
        render: (a) => e.createElement(
          M,
          {
            style: {
              background: n.colorInfoBg,
              border: `1px solid ${n.colorInfoBorder}`,
              color: n.colorInfoText
            }
          },
          a
        )
      },
      {
        title: "标题",
        dataIndex: "title",
        key: "title",
        render: (a) => e.createElement(X, { strong: !0 }, a)
      },
      {
        title: "优先级",
        key: "priority",
        width: 70,
        render: (a, S) => {
          const u = S.priority;
          return e.createElement(
            M,
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
        render: (a, S) => {
          const u = S.acceptanceCriteria;
          return typeof u == "string" ? e.createElement(
            "div",
            {
              style: {
                fontSize: 12,
                color: n.colorTextSecondary,
                whiteSpace: "pre-wrap"
              }
            },
            u.length > 100 ? u.slice(0, 100) + "..." : u
          ) : Array.isArray(u) ? e.createElement(
            "div",
            { style: { fontSize: 12, color: n.colorTextSecondary } },
            u.length > 2 ? u.slice(0, 2).join(", ") + "..." : u.join(", ")
          ) : "-";
        }
      }
    ], oe = e.createElement(
      J,
      { size: 8 },
      qe ? e.createElement(qe, { style: { color: "#1677ff" } }) : null,
      e.createElement(
        "span",
        { style: { fontSize: 14 } },
        e.createElement(X, { strong: !0 }, r.project || "PRD")
      )
    ), P = e.createElement(W, {
      columns: $,
      dataSource: Q.map((a) => ({ ...a, key: a.id })),
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
          border: `1px solid ${n.colorBorder}`,
          overflow: "hidden",
          background: n.colorBgContainer,
          padding: "12px 16px",
          margin: "4px 0"
        }
      },
      e.createElement("div", { style: { marginBottom: 8 } }, oe),
      e.createElement(ce, {
        size: "small",
        column: { xs: 1, sm: 2, md: 3 },
        style: { marginBottom: 12 },
        bordered: !1,
        items: [
          {
            key: "progress",
            label: "进度",
            children: `${_}/${U.length} 完成`
          }
        ]
      }),
      P,
      e.createElement(
        "div",
        {
          style: {
            fontSize: 11,
            color: n.colorTextTertiary,
            display: "flex",
            alignItems: "center",
            gap: 8
          }
        },
        Oe ? e.createElement(Oe, {
          style: { color: "#52c41a", fontSize: 14 }
        }) : "✅",
        e.createElement("span", null, "已完成"),
        e.createElement("span", { style: { margin: "0 4px" } }, "·"),
        Be ? e.createElement(Be, {
          style: { color: "#faad14", fontSize: 14 }
        }) : "🕐",
        e.createElement("span", null, "待处理")
      )
    );
  }
  const {
    Form: ue,
    Select: Ne,
    Drawer: kt,
    Modal: Ze,
    Empty: Tt,
    Badge: et,
    Divider: Ct,
    message: re
  } = F, {
    ApiOutlined: tt,
    PlusOutlined: nt,
    ReloadOutlined: Me,
    DeleteOutlined: rt,
    LinkOutlined: ot
  } = Y || {}, { useEffect: lt } = e, Ce = "/a2a/agents";
  function De() {
    var t;
    try {
      const n = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage");
      if (n) {
        const r = JSON.parse(n);
        return ((t = r == null ? void 0 : r.state) == null ? void 0 : t.selectedAgent) || null;
      }
    } catch {
    }
    return null;
  }
  async function ve(t, n) {
    const r = q(t), i = K == null ? void 0 : K(), c = De(), d = {
      "Content-Type": "application/json",
      ...i ? { Authorization: `Bearer ${i}` } : {},
      ...c ? { "X-Agent-Id": c } : {}
    }, s = await fetch(r, {
      ...n,
      headers: { ...d, ...(n == null ? void 0 : n.headers) || {} }
    });
    if (!s.ok) {
      const m = await s.text().catch(() => "");
      throw new Error(m || `HTTP ${s.status}`);
    }
    return s.status === 204 || s.headers.get("content-length") === "0" ? null : s.json();
  }
  function vt(t) {
    var m;
    const { agent: n, onClick: r } = t, i = n.status === "connected", c = i ? "#52c41a" : n.status === "error" ? "#ff4d4f" : "#d9d9d9", d = i ? "已连接" : n.status === "error" ? "错误" : "未连接", s = {
      gateway: "阿里云Agent Hub",
      bearer: "Bearer Token",
      api_key: "API Key"
    };
    return e.createElement(
      G,
      {
        hoverable: !0,
        onClick: r,
        size: "small",
        style: { cursor: "pointer" },
        title: e.createElement(
          J,
          null,
          e.createElement(et, { color: c }),
          e.createElement(
            "span",
            null,
            n.name || n.alias || n.url
          )
        ),
        extra: n.auth_type ? e.createElement(
          M,
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
          ot ? e.createElement(ot, { style: { marginRight: 4 } }) : null,
          n.url
        ),
        n.description ? e.createElement(
          "div",
          { style: { marginBottom: 4, color: "#999" } },
          n.description
        ) : null,
        ((m = n.skills) == null ? void 0 : m.length) > 0 ? e.createElement(
          "div",
          null,
          n.skills.slice(0, 3).map(
            (l, I) => e.createElement(
              M,
              { key: I, style: { fontSize: 11 } },
              l.name
            )
          ),
          n.skills.length > 3 ? e.createElement(
            M,
            { style: { fontSize: 11 } },
            `+${n.skills.length - 3}`
          ) : null
        ) : null,
        e.createElement(
          "div",
          { style: { marginTop: 4, color: c, fontSize: 11 } },
          d,
          n.error ? ` - ${n.error}` : ""
        )
      )
    );
  }
  function It() {
    const t = e.useRef(De()), [n, r] = T(t.current);
    return lt(() => {
      const i = () => {
        const d = De();
        d !== t.current && (t.current = d, r(d));
      }, c = setInterval(i, 200);
      return window.addEventListener("storage", i), () => {
        clearInterval(c), window.removeEventListener("storage", i);
      };
    }, []), n;
  }
  function _t() {
    var ut, mt;
    const { token: t } = $e.useToken(), n = It(), [r, i] = T([]), [c, d] = T(!0), [s, m] = T(!1), [l, I] = T(null), [w, O] = T(!1), [V, U] = T(!1), [Q, _] = T(!1), [$] = ue.useForm(), [oe, P] = T(!1), [a, S] = T(!1), [u, L] = T([]), [le, Z] = T(
      /* @__PURE__ */ new Set()
    ), [Se, pe] = T(
      []
    ), [me, fe] = T(1), ee = e.useRef(null), ge = 10, H = Ee(
      () => new Set(r.map((o) => o.url)),
      [r]
    ), y = e.useRef(H);
    y.current = H;
    const p = D(async () => {
      d(!0);
      try {
        const o = await ve(Ce);
        i((o == null ? void 0 : o.agents) || []);
      } catch {
        i([]);
      } finally {
        d(!1);
      }
    }, []);
    lt(() => {
      p();
    }, [n]);
    const R = D(() => {
      O(!0), I(null), m(!0), $.resetFields(), $.setFieldsValue({
        url: "",
        alias: "",
        auth_type: "",
        auth_token: ""
      });
    }, [$]), g = D((o) => {
      O(!1), I(o), m(!0);
    }, []), C = D(() => {
      m(!1), I(null), O(!1), $.resetFields();
    }, [$]), k = D(async () => {
      let o;
      try {
        o = await $.validateFields();
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
        U(!0);
        try {
          await ve(Ce, {
            method: "POST",
            body: JSON.stringify(E)
          }), re.success("A2A Agent 注册成功"), await p(), C();
        } catch (A) {
          re.error(A.message || "注册失败");
        } finally {
          U(!1);
        }
      }
    }, [$, p, C]), f = D(async () => {
      if (!l) return;
      const o = l.alias || l.url;
      Ze.confirm({
        title: `删除 ${o}`,
        content: "确定删除该远程 A2A Agent 吗？此操作不可撤销。",
        okText: "删除",
        cancelText: "取消",
        okButtonProps: { danger: !0 },
        async onOk() {
          try {
            await ve(`${Ce}/${encodeURIComponent(o)}`, {
              method: "DELETE"
            }), re.success("A2A Agent 已删除"), await p(), C();
          } catch (E) {
            re.error(E.message || "删除失败");
          }
        }
      });
    }, [l, p, C]), h = D(async () => {
      if (!l) return;
      const o = l.alias || l.url;
      _(!0);
      try {
        const E = await ve(
          `${Ce}/${encodeURIComponent(o)}/refresh`,
          {
            method: "POST"
          }
        );
        re.success("Agent Card 已刷新"), await p(), E && I(E);
      } catch (E) {
        re.error(E.message || "刷新失败");
      } finally {
        _(!1);
      }
    }, [l, p]), x = D(() => {
      P(!0), L([]), Z(/* @__PURE__ */ new Set()), pe([]), fe(1), ee.current = null, se();
    }, []), z = D(() => {
      a && ee.current && ee.current.abort(), P(!1), L([]), Z(/* @__PURE__ */ new Set()), pe([]), fe(1), ee.current = null;
    }, [a]), se = D(async () => {
      S(!0);
      const o = new AbortController();
      ee.current = o;
      try {
        const E = K == null ? void 0 : K(), A = De(), Ae = {
          ...E ? { Authorization: `Bearer ${E}` } : {},
          ...A ? { "X-Agent-Id": A } : {}
        }, be = await fetch(q("/a2a/import"), {
          method: "GET",
          headers: Ae,
          signal: o.signal
        });
        if (!be.ok) {
          const ze = await be.text().catch(() => "");
          throw new Error(ze || `HTTP ${be.status}`);
        }
        const Re = await be.json(), Je = (Re == null ? void 0 : Re.agents) || [];
        if (Je.length === 0) {
          re.warning("未找到可用的 Agent");
          return;
        }
        L(Je);
        const Mt = y.current;
        Z(
          new Set(
            Je.filter((ze) => !Mt.has(ze.url)).map((ze) => ze.url)
          )
        );
      } catch (E) {
        if ((E == null ? void 0 : E.name) === "AbortError") return;
        re.error(E.message || "获取 Agent 列表失败");
      } finally {
        S(!1), ee.current = null;
      }
    }, []), B = D((o) => {
      Z((E) => {
        const A = new Set(E);
        return A.has(o) ? A.delete(o) : A.add(o), A;
      });
    }, []), we = D(() => {
      Z(
        new Set(
          u.filter((o) => !H.has(o.url)).map((o) => o.url)
        )
      );
    }, [u, H]), N = D(() => {
      Z(/* @__PURE__ */ new Set());
    }, []), j = D(async () => {
      const o = u.filter(
        (A) => le.has(A.url) && !H.has(A.url)
      );
      if (o.length === 0) {
        re.warning("请至少选择一个 Agent");
        return;
      }
      S(!0), pe([]);
      const E = [];
      for (const A of o) {
        try {
          await ve(Ce, {
            method: "POST",
            body: JSON.stringify({
              url: A.url,
              alias: A.name || void 0,
              auth_type: A.auth_type || "gateway",
              auth_token: ""
            })
          }), E.push({ name: A.name || A.url, success: !0 });
        } catch (Ae) {
          E.push({
            name: A.name || A.url,
            success: !1,
            error: Ae.message || "注册失败"
          });
        }
        pe([...E]);
      }
      await p(), re.success(
        `导入完成：成功 ${E.filter((A) => A.success).length} 个，失败 ${E.filter((A) => !A.success).length} 个`
      ), S(!1), setTimeout(() => z(), 1500);
    }, [u, le, p, H]), ae = ((ut = ue.useWatch) == null ? void 0 : ut.call(ue, "auth_type", $)) ?? "", ie = e.createElement(
      ue,
      { form: $, layout: "vertical" },
      e.createElement(
        ue.Item,
        {
          name: "url",
          label: "Agent URL",
          rules: [{ required: !0, message: "请输入 Agent URL" }]
        },
        e.createElement(ne, {
          placeholder: "https://agent.example.com"
        })
      ),
      e.createElement(
        ue.Item,
        { name: "alias", label: "别名" },
        e.createElement(ne, { placeholder: "输入别名（可选）" })
      ),
      e.createElement(
        ue.Item,
        { name: "auth_type", label: "认证类型" },
        e.createElement(
          Ne,
          { allowClear: !0, placeholder: "无认证" },
          e.createElement(
            Ne.Option,
            { value: "bearer" },
            "Bearer Token"
          ),
          e.createElement(Ne.Option, { value: "api_key" }, "API Key"),
          e.createElement(
            Ne.Option,
            { value: "gateway" },
            "阿里云Agent Hub"
          )
        )
      ),
      ae === "gateway" ? e.createElement(
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
      ae && ae !== "gateway" ? e.createElement(
        ue.Item,
        { name: "auth_token", label: "认证凭证" },
        e.createElement(ne.Password, {
          placeholder: "Bearer Token 或 API Key"
        })
      ) : null
    ), ye = l ? e.createElement(
      "div",
      null,
      e.createElement(
        ce,
        { column: 1, bordered: !0, size: "small" },
        e.createElement(
          ce.Item,
          { label: "URL" },
          l.url
        ),
        e.createElement(
          ce.Item,
          { label: "别名" },
          l.alias || "-"
        ),
        e.createElement(
          ce.Item,
          { label: "Agent 名称" },
          l.name || "-"
        ),
        e.createElement(
          ce.Item,
          { label: "状态" },
          e.createElement(et, {
            color: l.status === "connected" ? "#52c41a" : l.status === "error" ? "#ff4d4f" : "#d9d9d9",
            text: l.status === "connected" ? "已连接" : l.status === "error" ? "错误" : "未连接"
          })
        ),
        e.createElement(
          ce.Item,
          { label: "认证类型" },
          l.auth_type ? e.createElement(
            M,
            { color: "blue" },
            {
              gateway: "阿里云Agent Hub",
              bearer: "Bearer Token",
              api_key: "API Key"
            }[l.auth_type] || l.auth_type
          ) : "无认证"
        ),
        e.createElement(
          ce.Item,
          { label: "描述" },
          l.description || "-"
        ),
        e.createElement(
          ce.Item,
          { label: "版本" },
          l.version || "-"
        )
      ),
      ((mt = l.skills) == null ? void 0 : mt.length) > 0 ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "技能"),
        ...l.skills.map(
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
      l.capabilities ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "能力"),
        e.createElement(
          J,
          null,
          e.createElement(
            M,
            {
              color: l.capabilities.streaming ? "green" : "default"
            },
            "Streaming"
          ),
          e.createElement(
            M,
            {
              color: l.capabilities.push_notifications ? "green" : "default"
            },
            "Push Notifications"
          )
        )
      ) : null,
      l.error ? e.createElement(
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
        l.error
      ) : null,
      e.createElement(Ct, null),
      e.createElement(
        J,
        null,
        e.createElement(
          b,
          {
            type: "primary",
            icon: Me ? e.createElement(Me) : null,
            loading: Q,
            onClick: h
          },
          "刷新 Agent Card"
        ),
        e.createElement(
          b,
          {
            danger: !0,
            icon: rt ? e.createElement(rt) : null,
            onClick: f
          },
          "删除"
        )
      )
    ) : null, v = e.createElement(
      kt,
      {
        title: w ? "注册远程 A2A Agent" : (l == null ? void 0 : l.name) || (l == null ? void 0 : l.alias) || "Agent 详情",
        open: s,
        onClose: C,
        width: 480,
        footer: w ? e.createElement(
          J,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(b, { onClick: C }, "取消"),
          e.createElement(
            b,
            { type: "primary", loading: V, onClick: k },
            "注册"
          )
        ) : null
      },
      w ? ie : ye
    ), te = e.createElement(
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
              icon: Me ? e.createElement(Me) : null,
              onClick: p,
              loading: c
            },
            "刷新列表"
          ),
          e.createElement(
            b,
            {
              icon: tt ? e.createElement(tt) : null,
              onClick: x
            },
            "从阿里云AgentHub导入"
          ),
          e.createElement(
            b,
            {
              type: "primary",
              icon: nt ? e.createElement(nt) : null,
              onClick: R
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
        Pe ? e.createElement(Pe, {
          style: { marginRight: 4, color: "#faad14" }
        }) : null,
        "当前 A2A 功能仅支持 CloudPaw 插件连接阿里云 Skills 门户 Agent，连接其他 Agent 可能存在不兼容问题。"
      )
    ), Le = c ? e.createElement(
      "div",
      { style: { textAlign: "center", padding: 60 } },
      e.createElement(he, { size: "large" })
    ) : r.length === 0 ? e.createElement(Tt, {
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
      ...r.map(
        (o) => e.createElement(vt, {
          key: o.alias || o.url,
          agent: o,
          onClick: () => g(o)
        })
      )
    ), xe = Se.length > 0, _e = Math.ceil(u.length / ge), dt = (me - 1) * ge, Bt = u.slice(dt, dt + ge), Nt = e.createElement(
      Ze,
      {
        title: xe ? "导入结果" : "从阿里云AgentHub导入 Agent",
        open: oe,
        onCancel: z,
        closable: !a || xe,
        maskClosable: !a || xe,
        width: 800,
        footer: xe ? e.createElement(
          J,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            b,
            { type: "primary", onClick: z },
            "关闭"
          )
        ) : u.length > 0 ? e.createElement(
          J,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            b,
            { onClick: z },
            "取消"
          ),
          e.createElement(
            b,
            {
              type: "primary",
              loading: a,
              disabled: le.size === 0,
              onClick: j
            },
            `确认导入 (${le.size}/${u.length})`
          )
        ) : null
      },
      // Loading state
      a && u.length === 0 && e.createElement(
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
        e.createElement(he, { size: "large" }),
        e.createElement(
          "span",
          { style: { fontSize: 13, color: t.colorTextTertiary } },
          "正在从 AgentHub 获取 Agent 列表..."
        )
      ),
      // Agent selection list
      !a && u.length > 0 && e.createElement(
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
            `共 ${u.length} 个 Agent，已选 ${le.size} 个`
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
                onClick: N
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
          ...Bt.map((o, E) => {
            var Ae;
            const A = le.has(o.url);
            return e.createElement(
              "div",
              {
                key: E,
                style: {
                  display: "flex",
                  gap: 8,
                  padding: 10,
                  border: A ? `1px solid ${t.colorInfo}` : `1px solid ${t.colorBorderSecondary}`,
                  borderRadius: 6,
                  cursor: H.has(o.url) ? "default" : "pointer",
                  background: H.has(o.url) ? t.colorBgLayout : A ? t.colorInfoBg : t.colorBgContainer,
                  transition: "all 0.15s ease",
                  opacity: H.has(o.url) ? 0.7 : 1
                },
                onClick: () => {
                  H.has(o.url) || B(o.url);
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
                      color: t.colorTextTertiary,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap"
                    }
                  },
                  o.description
                ) : null,
                ((Ae = o.skills) == null ? void 0 : Ae.length) > 0 ? e.createElement(
                  "div",
                  { style: { marginTop: 4 } },
                  ...o.skills.slice(0, 3).map(
                    (be, Re) => e.createElement(
                      M,
                      {
                        key: Re,
                        style: {
                          fontSize: 10,
                          marginRight: 4
                        }
                      },
                      be.name
                    )
                  ),
                  o.skills.length > 3 ? e.createElement(
                    M,
                    { style: { fontSize: 10 } },
                    `+${o.skills.length - 3}`
                  ) : null
                ) : null
              ),
              H.has(o.url) ? e.createElement(
                M,
                {
                  style: {
                    background: t.colorSuccessBg,
                    border: `1px solid ${t.colorSuccessBorder}`,
                    color: t.colorSuccessText,
                    fontSize: 10,
                    flexShrink: 0,
                    height: 20
                  }
                },
                "已导入"
              ) : null
            );
          })
        ),
        // Pagination
        _e > 1 && e.createElement(
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
              disabled: me === 1,
              onClick: () => fe((o) => o - 1)
            },
            "上一页"
          ),
          e.createElement(
            "span",
            { style: { fontSize: 12, color: t.colorTextTertiary } },
            `${me} / ${_e}`
          ),
          e.createElement(
            b,
            {
              size: "small",
              disabled: me === _e,
              onClick: () => fe((o) => o + 1)
            },
            "下一页"
          )
        )
      ),
      // Import results
      xe && e.createElement(
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
        ...Se.map(
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
                background: o.success ? t.colorInfoBg : t.colorErrorBg,
                border: o.success ? `1px solid ${t.colorInfo}` : `1px solid ${t.colorErrorBorder}`,
                fontSize: 12
              }
            },
            e.createElement(
              "span",
              {
                style: {
                  color: o.success ? t.colorSuccess : t.colorError,
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
                  color: o.success ? t.colorText : t.colorError
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
      te,
      Le,
      v,
      Nt
    );
  }
  function Rt({ data: t }) {
    var ee, ge, H;
    const { token: n } = $e.useToken(), r = e.useRef(null), [i, c] = T({}), d = Ee(() => {
      var p, R, g;
      const y = (g = (R = (p = t == null ? void 0 : t.content) == null ? void 0 : p[0]) == null ? void 0 : R.data) == null ? void 0 : g.arguments;
      if (!y) return null;
      try {
        return JSON.parse(y);
      } catch {
        return null;
      }
    }, [(H = (ge = (ee = t == null ? void 0 : t.content) == null ? void 0 : ee[0]) == null ? void 0 : ge.data) == null ? void 0 : H.arguments]), { toolResult: s, rawErrorText: m } = Ee(() => {
      var p;
      const y = t == null ? void 0 : t.content;
      if (!Array.isArray(y))
        return { toolResult: null, rawErrorText: "" };
      for (const R of y) {
        const g = (p = R == null ? void 0 : R.data) == null ? void 0 : p.output;
        if (!g) continue;
        let C = "";
        if (Array.isArray(g)) {
          const k = g.find(
            (f) => (f == null ? void 0 : f.type) === "text" && (f == null ? void 0 : f.text)
          );
          C = (k == null ? void 0 : k.text) || "";
        } else if (typeof g == "string")
          try {
            const k = JSON.parse(g);
            if (typeof k == "object" && (k != null && k.steps || k != null && k.response_text))
              return { toolResult: k, rawErrorText: "" };
            if (Array.isArray(k)) {
              const f = k.find((h) => (h == null ? void 0 : h.type) === "text" && (h == null ? void 0 : h.text));
              f != null && f.text && (C = f.text);
            }
          } catch {
            C = g;
          }
        if (C)
          try {
            return { toolResult: JSON.parse(C), rawErrorText: "" };
          } catch {
            return { toolResult: null, rawErrorText: C };
          }
      }
      return { toolResult: null, rawErrorText: "" };
    }, [t == null ? void 0 : t.content]), l = (s == null ? void 0 : s.steps) || [], I = (s == null ? void 0 : s.task_state) || "", w = (s == null ? void 0 : s.error) || "", O = (s == null ? void 0 : s.response_text) || "";
    e.useEffect(() => {
      r.current && (r.current.scrollTop = r.current.scrollHeight);
    }, [l.length, O, m]), e.useEffect(() => {
      const y = { ...i };
      let p = !1;
      l.forEach((R, g) => {
        i[g] === void 0 && (R.type === "thinking" && R.done || R.type === "tool_call" && R.status !== "running") && (y[g] = !0, p = !0);
      }), p && c(y);
    }, [l]);
    const V = (d == null ? void 0 : d.agent_alias) || "", U = (d == null ? void 0 : d.agent_url) || "", Q = V || U || "远程 Agent", _ = {
      completed: { color: "#52c41a", text: "已完成" },
      TASK_STATE_COMPLETED: { color: "#52c41a", text: "已完成" },
      failed: { color: "#ff4d4f", text: "失败" },
      TASK_STATE_FAILED: { color: "#ff4d4f", text: "失败" },
      error: { color: "#ff4d4f", text: "出错" },
      canceled: { color: "#faad14", text: "已取消" },
      TASK_STATE_CANCELED: { color: "#faad14", text: "已取消" },
      AWAITING_USER_INPUT: { color: "#1677ff", text: "等待输入" },
      input_required: { color: "#1677ff", text: "等待输入" }
    }, P = (s !== null || !!m) && !(I === "working" || I === "TASK_STATE_WORKING");
    let a = "#1677ff", S = "执行中...";
    P && (_[I] ? (a = _[I].color, S = _[I].text) : m ? (a = "#ff4d4f", S = "出错") : (a = "#52c41a", S = "已完成"));
    const u = e.createElement(
      J,
      { size: 6 },
      e.createElement("span", { style: { fontSize: 13 } }, "🔗"),
      e.createElement(
        X,
        { style: { fontSize: 12, color: "#595959" } },
        `A2A: ${Q}`
      ),
      e.createElement(
        M,
        { color: a, style: { fontSize: 11, lineHeight: "18px" } },
        S
      )
    ), L = l.length === 0 && !m && !w, le = !P && L ? e.createElement(
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
      e.createElement(he, { size: "small" }),
      e.createElement(
        X,
        { style: { fontSize: 12, color: "#52c41a" } },
        `正在连接 ${Q}...`
      )
    ) : null;
    function Z(y) {
      c((p) => ({
        ...p,
        [y]: !p[y]
      }));
    }
    function Se(y, p) {
      const R = !!i[p];
      if (y.type === "thinking") {
        const g = !!y.done, C = g ? "💭" : "🧠", k = g ? "思考完成" : "思考中...", f = e.createElement(
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
            onClick: g ? () => Z(p) : void 0
          },
          g && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            R ? "▶" : "▼"
          ),
          e.createElement("span", null, C),
          e.createElement("span", null, k),
          !g && e.createElement(he, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return R ? f : e.createElement(
          "div",
          { key: `step-${p}` },
          f,
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
        const g = y.status === "running", C = y.status === "error", k = g ? "⚙️" : C ? "❌" : "✅", f = g ? `正在执行: ${y.name}` : C ? `执行失败: ${y.name}` : `执行完成: ${y.name}`, h = g ? "#1677ff" : C ? "#ff4d4f" : "#52c41a", x = e.createElement(
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
            onClick: g ? void 0 : () => Z(p)
          },
          !g && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            R ? "▶" : "▼"
          ),
          e.createElement("span", null, k),
          e.createElement("span", null, f),
          g && e.createElement(he, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return R || !y.desc && !g ? x : e.createElement(
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
                color: n.colorTextTertiary
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
    const pe = l.length > 0 ? e.createElement(
      "div",
      {
        ref: r,
        style: {
          background: "#fafafa",
          border: "1px solid #e8e8e8",
          borderRadius: 6,
          padding: "6px 10px",
          maxHeight: 200,
          overflowY: "auto"
        }
      },
      ...l.map(Se)
    ) : null, me = m || w ? e.createElement(
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
      w ? `错误: ${w}` : m
    ) : null, fe = !l.length && O && !m ? e.createElement(
      "div",
      {
        ref: r,
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
        O
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
      le,
      pe,
      fe,
      me
    );
  }
  const zt = "__A2A_STREAM_START__", $t = "A2A_STREAM_START", Ie = /* @__PURE__ */ new Set();
  function je(t) {
    return t ? t.includes(zt) || t.includes($t) : !1;
  }
  function We(t) {
    var n, r;
    return t.getAttribute("data-msg-id") || t.getAttribute("data-message-id") || ((n = t.closest("[data-msg-id]")) == null ? void 0 : n.getAttribute("data-msg-id")) || ((r = t.closest("[data-message-id]")) == null ? void 0 : r.getAttribute("data-message-id")) || null;
  }
  function Pt(t) {
    if (je(t.innerHTML) || je(t.textContent))
      return t;
    const n = document.createTreeWalker(
      t,
      NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT
    );
    for (; n.nextNode(); ) {
      const r = n.currentNode, i = r.nodeType === Node.TEXT_NODE ? r.textContent : r.innerHTML;
      if (je(i)) {
        const c = r.nodeType === Node.TEXT_NODE ? r.parentElement : r;
        if (c) return c;
      }
    }
    return null;
  }
  async function Fe(t) {
    var l, I;
    const n = window.QwenPaw;
    if (!(n != null && n.host)) {
      console.warn("[a2a] QwenPaw.host not available");
      return;
    }
    const { getApiUrl: r, getApiToken: i } = n.host, c = r("/a2a/call/stream"), d = i();
    console.log("[a2a] Subscribing to SSE stream:", c);
    const s = document.createElement("div");
    s.style.cssText = "background:#f6ffed;border:1px solid #b7eb8f;border-radius:8px;padding:12px 16px;margin:4px 0;font-size:13px;white-space:pre-wrap;word-break:break-word;color:#262626;min-height:24px;", s.textContent = "正在连接远程 Agent...", t.textContent = "", t.appendChild(s);
    const m = new AbortController();
    try {
      const w = {
        Accept: "text/event-stream"
      };
      d && (w.Authorization = `Bearer ${d}`);
      try {
        const _ = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage"), $ = (I = (l = JSON.parse(_ || "{}")) == null ? void 0 : l.state) == null ? void 0 : I.selectedAgent;
        $ && (w["X-Agent-Id"] = $);
      } catch {
      }
      console.log("[a2a] Fetching SSE with headers:", w);
      const O = await fetch(c, { headers: w, signal: m.signal });
      if (console.log("[a2a] SSE response status:", O.status), !O.ok) {
        const _ = await O.text().catch(() => "");
        s.textContent = `SSE 连接失败 (${O.status}): ${_.slice(
          0,
          100
        )}`, s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0";
        return;
      }
      if (!O.body) {
        s.textContent = "SSE 连接失败：无响应体", s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0";
        return;
      }
      const V = O.body.getReader(), U = new TextDecoder();
      let Q = "";
      for (; ; ) {
        const { done: _, value: $ } = await V.read();
        if (_) {
          console.log("[a2a] SSE stream ended (done)");
          break;
        }
        Q += U.decode($, { stream: !0 });
        const oe = Q.split(`
`);
        Q = oe.pop() || "";
        for (const P of oe)
          if (P.startsWith("data: "))
            try {
              const a = JSON.parse(P.slice(6));
              if (console.log("[a2a] SSE event:", a), a.done) {
                a.error && (s.textContent = `错误: ${a.error}`, s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0"), console.log("[a2a] SSE done signal received");
                return;
              }
              typeof a.response_text == "string" && a.response_text && (s.textContent = a.response_text);
            } catch (a) {
              console.warn("[a2a] SSE parse error:", a, "line:", P);
            }
      }
    } catch (w) {
      (w == null ? void 0 : w.name) !== "AbortError" && (console.error("[a2a] SSE subscription error:", w), s.textContent = `连接出错: ${(w == null ? void 0 : w.message) || w}`, s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0");
    }
  }
  function Ot() {
    console.log("[a2a] Initializing stream interceptor");
    function t(c) {
      if (c.nodeType !== Node.ELEMENT_NODE) return;
      const d = c, s = We(d);
      if (s && Ie.has(s)) return;
      const m = Pt(d);
      m && (console.log("[a2a] Marker detected in DOM, msgId:", s), s && Ie.add(s), Fe(m));
    }
    new MutationObserver((c) => {
      for (const d of c) {
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
    const r = setInterval(() => {
      const c = document.evaluate(
        "//text()[contains(., 'A2A_STREAM_START')]",
        document.body,
        null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
        null
      );
      for (let d = 0; d < c.snapshotLength; d++) {
        const m = c.snapshotItem(d).parentElement;
        if (m) {
          const l = We(m);
          if (l && Ie.has(l)) continue;
          console.log("[a2a] Marker found in periodic scan, msgId:", l), l && Ie.add(l), Fe(m);
        }
      }
    }, 500);
    window.addEventListener("beforeunload", () => clearInterval(r));
    const i = document.evaluate(
      "//text()[contains(., 'A2A_STREAM_START')]",
      document.body,
      null,
      XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
      null
    );
    for (let c = 0; c < i.snapshotLength; c++) {
      const s = i.snapshotItem(c).parentElement;
      if (s) {
        const m = We(s);
        m && Ie.add(m), console.log("[a2a] Marker found in existing DOM, msgId:", m), Fe(s);
      }
    }
  }
  (at = (st = window.QwenPaw).registerToolRender) == null || at.call(st, "cloudpaw", {
    proposal_choice: At,
    manage_prd: bt,
    a2a_call: Rt
  }), (ct = (it = window.QwenPaw).registerRoutes) == null || ct.call(it, "cloudpaw", [
    {
      path: "/a2a",
      component: _t,
      label: "A2A",
      icon: "🔗",
      priority: 10
    }
  ]), Lt(), Ht(), Ot();
}
function Lt() {
  const e = "qwenpaw-last-used-agent", F = "qwenpaw-agent-storage", Y = "cloudpaw-first-install", q = "cloud-orchestrator";
  if (localStorage.getItem(Y)) return;
  localStorage.setItem(Y, "true");
  function K() {
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
  K(), window.addEventListener(
    "beforeunload",
    () => {
      K();
    },
    { once: !0 }
  ), console.info(
    "[cloudpaw] Set default agent to cloud-orchestrator for first-time user"
  ), window.location.reload();
}
function Ht() {
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
  const Y = F.configProvider, q = Y.getConfig.bind(Y), K = "https://gw.alicdn.com/imgextra/i2/O1CN01pyXzjQ1EL1PuZMlSd_!!6000000000334-2-tps-288-288.png", G = {
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
  }, M = {
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
  function ke() {
    const b = localStorage.getItem("language") || "";
    return b ? b.split("-")[0] : (navigator.language || "").split("-")[0] || "en";
  }
  if (Y.getGreeting = () => G[ke()] || G.en, Y.getDescription = () => W[ke()] || W.en, Y.getPrompts = () => M[ke()] || M.en, Y.getConfig = function(b) {
    var Te;
    const ne = q(b);
    return {
      ...ne,
      theme: {
        ...ne.theme,
        leftHeader: {
          ...(Te = ne.theme) == null ? void 0 : Te.leftHeader,
          title: "Work with CloudPaw"
        }
      },
      welcome: {
        ...ne.welcome,
        avatar: K
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
Dt();
