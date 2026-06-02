function Dt() {
  var st, at, it, ct;
  const { React: e, antd: Y, antdIcons: Z, getApiUrl: ee, getApiToken: X } = window.QwenPaw.host, {
    Card: te,
    Table: K,
    Tag: H,
    Typography: ke,
    Space: q,
    Button: T,
    Input: le,
    Radio: Te,
    Descriptions: me,
    Tooltip: Je,
    Spin: Ee,
    message: Ke,
    theme: $e
  } = Y, { Text: ne } = ke, { TextArea: ft } = le, { useState: I, useMemo: xe, useCallback: j } = e, {
    InfoCircleOutlined: Pe,
    DownOutlined: Ye,
    RightOutlined: pt,
    CheckCircleOutlined: Oe,
    FieldTimeOutlined: Be,
    FileTextOutlined: qe
  } = Z || {};
  function Ge(t) {
    var a, i;
    const n = (i = (a = t == null ? void 0 : t.content) == null ? void 0 : a[0]) == null ? void 0 : i.data, r = n == null ? void 0 : n.arguments;
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
  function fe(t) {
    return typeof t == "string" ? t : t && typeof t == "object" && "text" in t ? t.text : String(t ?? "");
  }
  function yt(t) {
    if (t == null) return !0;
    const n = fe(t).trim();
    return !!(!n || /^[¥$]?0+(\.0+)?$/.test(n) || /^[-–—]+$/.test(n));
  }
  async function ht(t, n) {
    try {
      const r = X(), a = {
        "Content-Type": "application/json"
      };
      return r && (a.Authorization = `Bearer ${r}`), (await fetch(ee("/interaction"), {
        method: "POST",
        headers: a,
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
            (a) => (a == null ? void 0 : a.type) === "text" && (a == null ? void 0 : a.text)
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
    var s, d;
    if (!t || t.length < 2) return null;
    const n = (d = (s = t[1]) == null ? void 0 : s.data) == null ? void 0 : d.output, r = Xe(n);
    if (!r) return null;
    if (r.startsWith("Error:")) return r;
    const a = r.match(/^用户选择了「(.+?)」并确认部署$/);
    if (a) return `已确认部署「${a[1]}」`;
    const i = r.match(
      /^用户选择「(.+?)」并要求调整[：:](.+)$/
    );
    if (i)
      return `已选择「${i[1]}」并调整：${i[2]}`;
    if (r === "用户确认部署") return "已确认部署";
    const c = r.match(/^用户要求调整资源[：:](.+)$/);
    return c ? `已反馈调整意见：${c[1]}` : "已确认";
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
    const n = fe(t[0]).trim().toLowerCase();
    return xt.has(n);
  }
  function Ve(t) {
    if (!Array.isArray(t) || t.length !== 10) return !1;
    const n = fe(t[0]).trim();
    return /^(合计|总计|total)/i.test(n);
  }
  function St(t) {
    const n = [];
    let r = [];
    for (const a of t)
      r.push(a), Ve(a) && (n.push(r), r = []);
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
    var p, _, C;
    const { token: n } = $e.useToken(), [r, a] = I("confirm"), [i, c] = I(""), [s, d] = I(!1), [o, z] = I(null), [S, N] = I(
      {}
    ), M = e.useRef(!1), Q = e.useRef(null), [, V] = I(0), v = t == null ? void 0 : t.content, O = v && v.length >= 2 && ((_ = (p = v[1]) == null ? void 0 : p.data) == null ? void 0 : _.output), ae = xe(
      () => Et(v),
      [v]
    ), B = M.current || O || ae !== null, g = xe(() => {
      const u = Ge(t), h = u == null ? void 0 : u.data;
      if (!h) return null;
      try {
        const x = typeof h == "string" ? JSON.parse(h) : h;
        let P;
        if (u.strategy_names)
          try {
            const L = typeof u.strategy_names == "string" ? JSON.parse(u.strategy_names) : u.strategy_names;
            P = Array.isArray(L) ? L : [];
          } catch {
            P = [];
          }
        else x != null && x.proposal_names ? P = x.proposal_names : P = [];
        const ce = P.length >= 2 ? P.length : 0;
        let D;
        if (Array.isArray(x) && x.length > 0)
          if (Array.isArray(x[0]) && x[0].length === 10 && !Array.isArray(x[0][0])) {
            const J = x.filter(
              (ue) => !He(ue)
            );
            if (J.filter(
              (ue) => Ve(ue)
            ).length >= 2)
              D = St(J);
            else if (ce >= 2 && J.length >= ce * 2) {
              const ue = Math.ceil(J.length / ce);
              D = [];
              for (let he = 0; he < J.length; he += ue)
                D.push(J.slice(he, he + ue));
            } else
              D = [J];
          } else
            D = x.map(
              (J) => J.filter(
                (de) => Array.isArray(de) && de.length === 10 && !He(de)
              )
            );
        else if (x != null && x.proposals)
          D = x.proposals.map(
            (L) => L.filter((J) => !He(J))
          );
        else
          return null;
        if (D = D.filter((L) => L.length > 0), D.length === 0) return null;
        const we = ["方案一", "方案二", "方案三", "方案四", "方案五"];
        if (P.length < D.length)
          for (let L = P.length; L < D.length; L++)
            P.push(we[L] || `方案${L + 1}`);
        return { proposals: D, names: P };
      } catch {
        return null;
      }
    }, [t]), W = gt(), A = (((C = g == null ? void 0 : g.proposals) == null ? void 0 : C.length) ?? 0) > 1, ie = j(async () => {
      if (!W || B || !g) return;
      const u = A ? o : 0, h = g.names[u ?? 0] || `方案${(u ?? 0) + 1}`;
      let x;
      r === "confirm" ? x = `用户选择了「${h}」并确认部署` : x = `用户选择「${h}」并要求调整：${i.trim() || "未填写具体要求"}`, d(!0);
      const P = await ht(W, x);
      d(!1), P ? (M.current = !0, r === "confirm" ? Q.current = `已确认部署「${h}」` : Q.current = `已选择「${h}」并调整：${i.trim()}`, V((ce) => ce + 1), Ke.success(
        r === "confirm" ? "已确认部署方案" : "已提交调整意见"
      )) : Ke.error("操作失败，请重试");
    }, [
      W,
      B,
      g,
      r,
      i,
      o,
      A
    ]), m = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created";
    if (!g)
      return m ? e.createElement(
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
        e.createElement(Ee, { size: "default" }),
        e.createElement(
          ne,
          { type: "secondary", style: { fontSize: 13 } },
          "正在生成资源方案..."
        )
      ) : e.createElement(
        te,
        { size: "small", style: { margin: "4px 0" } },
        e.createElement(ne, { type: "secondary" }, "无法解析方案数据")
      );
    const { proposals: b, names: k } = g, U = Qe.map((u, h) => ({
      title: u,
      dataIndex: `col_${h}`,
      key: `col_${h}`,
      render: (x) => wt(x),
      ellipsis: h < 3
    }));
    let G = "待确认", ge = "processing";
    B && (ge = "success", G = Q.current || ae || "已确认");
    const re = e.createElement(
      H,
      {
        color: ge,
        style: { marginLeft: 4 }
      },
      G
    ), ye = e.createElement(
      q,
      { size: 8 },
      e.createElement("span", null, "☁️"),
      e.createElement(
        ne,
        { strong: !0, style: { fontSize: 14 } },
        B ? "资源配置方案" : "请确认您的资源配置方案"
      ),
      re
    ), F = b.map((u, h) => {
      const x = A ? o === h : !0, P = S[h] || !1, ce = (R) => {
        const oe = fe(R[0] || "").trim();
        return /^合计|^总计|^total/i.test(oe);
      }, D = u.find(ce), we = u.filter((R) => !ce(R)), L = we.map((R) => ({
        type: fe(R[0] || ""),
        purpose: fe(R[1] || ""),
        spec: fe(R[2] || ""),
        cost: R[9] ?? null
      })), J = D ? fe(D[9] ?? "") : "", de = u.map((R, oe) => {
        const Le = { key: oe };
        return R.forEach((Se, _e) => {
          Le[`col_${_e}`] = Se;
        }), Le;
      }), ue = x ? `2px solid ${n.colorInfo}` : `1px solid ${n.colorBorderSecondary}`, he = x ? `0 0 0 2px ${n.colorInfoBg}` : "none";
      return e.createElement(
        "div",
        {
          key: h,
          style: {
            flex: 1,
            minWidth: 240,
            border: ue,
            borderRadius: 8,
            cursor: A ? "pointer" : "default",
            transition: "all 0.2s ease",
            boxShadow: he,
            background: n.colorBgContainer
          },
          onClick: A ? () => z(h) : void 0
        },
        e.createElement(
          "div",
          { style: { padding: "10px 12px" } },
          // Proposal name
          e.createElement(
            ne,
            {
              strong: !0,
              style: { fontSize: 14, display: "block", marginBottom: 8 }
            },
            k[h]
          ),
          ...L.map(
            (R, oe) => e.createElement(
              "div",
              {
                key: oe,
                style: {
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "4px 0",
                  borderBottom: oe < L.length - 1 ? `1px solid ${n.colorSplit}` : "none"
                }
              },
              e.createElement(
                "div",
                { style: { flex: 1, minWidth: 0 } },
                e.createElement(
                  "span",
                  { style: { fontSize: 12, color: n.colorText } },
                  R.type
                ),
                R.spec && e.createElement(
                  "span",
                  {
                    style: {
                      fontSize: 11,
                      color: n.colorTextTertiary,
                      marginLeft: 6
                    }
                  },
                  R.spec
                )
              ),
              !yt(R.cost) && e.createElement(
                "span",
                {
                  style: {
                    fontSize: 12,
                    color: n.colorTextSecondary,
                    flexShrink: 0,
                    marginLeft: 8
                  }
                },
                fe(R.cost)
              )
            )
          ),
          // Total cost
          J && e.createElement(
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
              J
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
              onClick: (R) => {
                R.stopPropagation(), N((oe) => ({
                  ...oe,
                  [h]: !oe[h]
                }));
              }
            },
            e.createElement(
              P && Ye ? Ye : pt || "span",
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
          P && e.createElement(
            "div",
            {
              onClick: (R) => R.stopPropagation(),
              style: { marginTop: 4, maxHeight: 260, overflow: "auto" }
            },
            e.createElement(K, {
              columns: U,
              dataSource: de,
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
    ), f = !B && W && !(A && o === null) && e.createElement(
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
            onClick: () => a("confirm")
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
              onClick: () => a("adjust")
            },
            e.createElement(Te, { checked: r === "adjust" }),
            e.createElement(
              "span",
              { style: { fontSize: 13 } },
              "调整资源"
            )
          ),
          r === "adjust" && e.createElement(ft, {
            value: i,
            onChange: (u) => c(u.target.value),
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
          ne,
          { type: "secondary", style: { fontSize: 11 } },
          A ? "一小时后未操作将自动选择第一个方案" : "一小时后未操作将自动确认部署"
        ),
        e.createElement(
          T,
          {
            type: "primary",
            size: "small",
            loading: s,
            onClick: ie,
            disabled: r === "adjust" && !i.trim()
          },
          r === "confirm" ? "确认部署" : "提交调整"
        )
      )
    ), $ = A && o === null && !B && e.createElement(
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
      e.createElement("div", { style: { marginBottom: 10 } }, ye),
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
        ...F
      ),
      $,
      y,
      !B && f
    );
  }
  function bt({ data: t }) {
    var ie;
    const { token: n } = $e.useToken(), [r, a] = I(null), [i, c] = I(!1), s = (t == null ? void 0 : t.status) === "in_progress" || (t == null ? void 0 : t.status) === "created", d = xe(() => {
      const m = Ge(t);
      return (m == null ? void 0 : m.loop_dir) || null;
    }, [t]), o = xe(() => {
      var b, k, U;
      const m = Xe((U = (k = (b = t == null ? void 0 : t.content) == null ? void 0 : b[1]) == null ? void 0 : k.data) == null ? void 0 : U.output);
      if (!m) return null;
      try {
        return JSON.parse(m);
      } catch {
        return null;
      }
    }, [t]), z = (o == null ? void 0 : o.status) === "ok", S = (o == null ? void 0 : o.status) === "error", N = S ? (o == null ? void 0 : o.message) || "未知错误" : null, M = ((ie = o == null ? void 0 : o.data) == null ? void 0 : ie.timestamp) || "", Q = e.useRef(null), V = j(async () => {
      if (d && !(M && Q.current === M))
        try {
          const m = X(), b = {};
          m && (b.Authorization = `Bearer ${m}`);
          const k = M ? `/prd?loop_dir=${encodeURIComponent(d)}&timestamp=${encodeURIComponent(M)}` : `/prd?loop_dir=${encodeURIComponent(d)}`, U = await fetch(ee(k), { headers: b });
          if (!U.ok) {
            c(!0);
            return;
          }
          const G = await U.json();
          G && Array.isArray(G.userStories) ? (M && (G.timestamp = M), Q.current = M, a(G), c(!1)) : c(!0);
        } catch {
          c(!0);
        }
    }, [d, M]);
    if (e.useEffect(() => {
      !s && z && d && V();
    }, [s, z, d, V]), s)
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
        e.createElement(Ee, { size: "default" }),
        e.createElement(
          ne,
          { type: "secondary", style: { fontSize: 13 } },
          "正在更新 PRD..."
        )
      );
    if (S)
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
          ne,
          { type: "danger", style: { fontSize: 13 } },
          `PRD 格式错误，将会修正：${N}`
        )
      );
    if (!z || i || !r) return null;
    const v = r.userStories, O = [...v].sort(
      (m, b) => (m.priority || 99) - (b.priority || 99)
    ), ae = v.filter((m) => m.passes).length, B = [
      {
        title: "状态",
        key: "status",
        width: 50,
        align: "center",
        render: (m, b) => {
          if (b.passes) {
            const U = Oe ? e.createElement(Oe, {
              style: { color: "#52c41a", fontSize: 18 }
            }) : "✅";
            return e.createElement(Je, { title: "已完成" }, U);
          }
          const k = Be ? e.createElement(Be, {
            style: { color: "#faad14", fontSize: 18 }
          }) : "🕐";
          return e.createElement(Je, { title: "待处理" }, k);
        }
      },
      {
        title: "ID",
        dataIndex: "id",
        key: "id",
        width: 85,
        render: (m) => e.createElement(
          H,
          {
            style: {
              background: n.colorInfoBg,
              border: `1px solid ${n.colorInfoBorder}`,
              color: n.colorInfoText
            }
          },
          m
        )
      },
      {
        title: "标题",
        dataIndex: "title",
        key: "title",
        render: (m) => e.createElement(ne, { strong: !0 }, m)
      },
      {
        title: "优先级",
        key: "priority",
        width: 70,
        render: (m, b) => {
          const k = b.priority;
          return e.createElement(
            H,
            { color: "default" },
            k != null ? String(k) : "-"
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
        render: (m, b) => {
          const k = b.acceptanceCriteria;
          return typeof k == "string" ? e.createElement(
            "div",
            {
              style: {
                fontSize: 12,
                color: n.colorTextSecondary,
                whiteSpace: "pre-wrap"
              }
            },
            k.length > 100 ? k.slice(0, 100) + "..." : k
          ) : Array.isArray(k) ? e.createElement(
            "div",
            { style: { fontSize: 12, color: n.colorTextSecondary } },
            k.length > 2 ? k.slice(0, 2).join(", ") + "..." : k.join(", ")
          ) : "-";
        }
      }
    ], g = e.createElement(
      q,
      { size: 8 },
      qe ? e.createElement(qe, { style: { color: "#1677ff" } }) : null,
      e.createElement(
        "span",
        { style: { fontSize: 14 } },
        e.createElement(ne, { strong: !0 }, r.project || "PRD")
      )
    ), W = e.createElement(K, {
      columns: B,
      dataSource: O.map((m) => ({ ...m, key: m.id })),
      size: "small",
      pagination: !1,
      scroll: { x: "max-content" },
      style: { marginBottom: 4 }
    }), A = [
      {
        key: "progress",
        label: "进度",
        children: `${ae}/${v.length} 完成`
      }
    ];
    return r.timestamp && A.push({
      key: "timestamp",
      label: "时间",
      children: r.timestamp
    }), e.createElement(
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
      e.createElement("div", { style: { marginBottom: 8 } }, g),
      e.createElement(me, {
        size: "small",
        column: { xs: 1, sm: 2, md: 3 },
        style: { marginBottom: 12 },
        bordered: !1,
        items: A
      }),
      W,
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
    Form: pe,
    Select: Ne,
    Drawer: kt,
    Modal: Ze,
    Empty: Tt,
    Badge: et,
    Divider: Ct,
    message: se
  } = Y, {
    ApiOutlined: tt,
    PlusOutlined: nt,
    ReloadOutlined: Me,
    DeleteOutlined: rt,
    LinkOutlined: ot
  } = Z || {}, { useEffect: lt } = e, Ce = "/a2a/agents";
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
  async function Ie(t, n) {
    const r = ee(t), a = X == null ? void 0 : X(), i = De(), c = {
      "Content-Type": "application/json",
      ...a ? { Authorization: `Bearer ${a}` } : {},
      ...i ? { "X-Agent-Id": i } : {}
    }, s = await fetch(r, {
      ...n,
      headers: { ...c, ...(n == null ? void 0 : n.headers) || {} }
    });
    if (!s.ok) {
      const d = await s.text().catch(() => "");
      throw new Error(d || `HTTP ${s.status}`);
    }
    return s.status === 204 || s.headers.get("content-length") === "0" ? null : s.json();
  }
  function It(t) {
    var d;
    const { agent: n, onClick: r } = t, a = n.status === "connected", i = a ? "#52c41a" : n.status === "error" ? "#ff4d4f" : "#d9d9d9", c = a ? "已连接" : n.status === "error" ? "错误" : "未连接", s = {
      gateway: "阿里云Agent Hub",
      bearer: "Bearer Token",
      api_key: "API Key"
    };
    return e.createElement(
      te,
      {
        hoverable: !0,
        onClick: r,
        size: "small",
        style: { cursor: "pointer" },
        title: e.createElement(
          q,
          null,
          e.createElement(et, { color: i }),
          e.createElement(
            "span",
            null,
            n.name || n.alias || n.url
          )
        ),
        extra: n.auth_type ? e.createElement(
          H,
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
        ((d = n.skills) == null ? void 0 : d.length) > 0 ? e.createElement(
          "div",
          null,
          n.skills.slice(0, 3).map(
            (o, z) => e.createElement(
              H,
              { key: z, style: { fontSize: 11 } },
              o.name
            )
          ),
          n.skills.length > 3 ? e.createElement(
            H,
            { style: { fontSize: 11 } },
            `+${n.skills.length - 3}`
          ) : null
        ) : null,
        e.createElement(
          "div",
          { style: { marginTop: 4, color: i, fontSize: 11 } },
          c,
          n.error ? ` - ${n.error}` : ""
        )
      )
    );
  }
  function vt() {
    const t = e.useRef(De()), [n, r] = I(t.current);
    return lt(() => {
      const a = () => {
        const c = De();
        c !== t.current && (t.current = c, r(c));
      }, i = setInterval(a, 200);
      return window.addEventListener("storage", a), () => {
        clearInterval(i), window.removeEventListener("storage", a);
      };
    }, []), n;
  }
  function _t() {
    var ut, mt;
    const { token: t } = $e.useToken(), n = vt(), [r, a] = I([]), [i, c] = I(!0), [s, d] = I(!1), [o, z] = I(null), [S, N] = I(!1), [M, Q] = I(!1), [V, v] = I(!1), [O] = pe.useForm(), [ae, B] = I(!1), [g, W] = I(!1), [A, ie] = I([]), [m, b] = I(
      /* @__PURE__ */ new Set()
    ), [k, U] = I(
      []
    ), [G, ge] = I(1), re = e.useRef(null), ye = 10, F = xe(
      () => new Set(r.map((l) => l.url)),
      [r]
    ), y = e.useRef(F);
    y.current = F;
    const f = j(async () => {
      c(!0);
      try {
        const l = await Ie(Ce);
        a((l == null ? void 0 : l.agents) || []);
      } catch {
        a([]);
      } finally {
        c(!1);
      }
    }, []);
    lt(() => {
      f();
    }, [n]);
    const $ = j(() => {
      N(!0), z(null), d(!0), O.resetFields(), O.setFieldsValue({
        url: "",
        alias: "",
        auth_type: "",
        auth_token: ""
      });
    }, [O]), p = j((l) => {
      N(!1), z(l), d(!0);
    }, []), _ = j(() => {
      d(!1), z(null), N(!1), O.resetFields();
    }, [O]), C = j(async () => {
      let l;
      try {
        l = await O.validateFields();
      } catch {
        return;
      }
      const E = {
        url: String(l.url || "").trim(),
        alias: String(l.alias || "").trim() || void 0,
        auth_type: String(l.auth_type || ""),
        auth_token: String(l.auth_token || "")
      };
      if (E.url) {
        Q(!0);
        try {
          await Ie(Ce, {
            method: "POST",
            body: JSON.stringify(E)
          }), se.success("A2A Agent 注册成功"), await f(), _();
        } catch (w) {
          se.error(w.message || "注册失败");
        } finally {
          Q(!1);
        }
      }
    }, [O, f, _]), u = j(async () => {
      if (!o) return;
      const l = o.alias || o.url;
      Ze.confirm({
        title: `删除 ${l}`,
        content: "确定删除该远程 A2A Agent 吗？此操作不可撤销。",
        okText: "删除",
        cancelText: "取消",
        okButtonProps: { danger: !0 },
        async onOk() {
          try {
            await Ie(`${Ce}/${encodeURIComponent(l)}`, {
              method: "DELETE"
            }), se.success("A2A Agent 已删除"), await f(), _();
          } catch (E) {
            se.error(E.message || "删除失败");
          }
        }
      });
    }, [o, f, _]), h = j(async () => {
      if (!o) return;
      const l = o.alias || o.url;
      v(!0);
      try {
        const E = await Ie(
          `${Ce}/${encodeURIComponent(l)}/refresh`,
          {
            method: "POST"
          }
        );
        se.success("Agent Card 已刷新"), await f(), E && z(E);
      } catch (E) {
        se.error(E.message || "刷新失败");
      } finally {
        v(!1);
      }
    }, [o, f]), x = j(() => {
      B(!0), ie([]), b(/* @__PURE__ */ new Set()), U([]), ge(1), re.current = null, ce();
    }, []), P = j(() => {
      g && re.current && re.current.abort(), B(!1), ie([]), b(/* @__PURE__ */ new Set()), U([]), ge(1), re.current = null;
    }, [g]), ce = j(async () => {
      W(!0);
      const l = new AbortController();
      re.current = l;
      try {
        const E = X == null ? void 0 : X(), w = De(), Ae = {
          ...E ? { Authorization: `Bearer ${E}` } : {},
          ...w ? { "X-Agent-Id": w } : {}
        }, be = await fetch(ee("/a2a/import"), {
          method: "GET",
          headers: Ae,
          signal: l.signal
        });
        if (!be.ok) {
          const ze = await be.text().catch(() => "");
          throw new Error(ze || `HTTP ${be.status}`);
        }
        const Re = await be.json(), Fe = (Re == null ? void 0 : Re.agents) || [];
        if (Fe.length === 0) {
          se.warning("未找到可用的 Agent");
          return;
        }
        ie(Fe);
        const Mt = y.current;
        b(
          new Set(
            Fe.filter((ze) => !Mt.has(ze.url)).map((ze) => ze.url)
          )
        );
      } catch (E) {
        if ((E == null ? void 0 : E.name) === "AbortError") return;
        se.error(E.message || "获取 Agent 列表失败");
      } finally {
        W(!1), re.current = null;
      }
    }, []), D = j((l) => {
      b((E) => {
        const w = new Set(E);
        return w.has(l) ? w.delete(l) : w.add(l), w;
      });
    }, []), we = j(() => {
      b(
        new Set(
          A.filter((l) => !F.has(l.url)).map((l) => l.url)
        )
      );
    }, [A, F]), L = j(() => {
      b(/* @__PURE__ */ new Set());
    }, []), J = j(async () => {
      const l = A.filter(
        (w) => m.has(w.url) && !F.has(w.url)
      );
      if (l.length === 0) {
        se.warning("请至少选择一个 Agent");
        return;
      }
      W(!0), U([]);
      const E = [];
      for (const w of l) {
        try {
          await Ie(Ce, {
            method: "POST",
            body: JSON.stringify({
              url: w.url,
              alias: w.name || void 0,
              auth_type: w.auth_type || "gateway",
              auth_token: ""
            })
          }), E.push({ name: w.name || w.url, success: !0 });
        } catch (Ae) {
          E.push({
            name: w.name || w.url,
            success: !1,
            error: Ae.message || "注册失败"
          });
        }
        U([...E]);
      }
      await f(), se.success(
        `导入完成：成功 ${E.filter((w) => w.success).length} 个，失败 ${E.filter((w) => !w.success).length} 个`
      ), W(!1), setTimeout(() => P(), 1500);
    }, [A, m, f, F]), de = ((ut = pe.useWatch) == null ? void 0 : ut.call(pe, "auth_type", O)) ?? "", ue = e.createElement(
      pe,
      { form: O, layout: "vertical" },
      e.createElement(
        pe.Item,
        {
          name: "url",
          label: "Agent URL",
          rules: [{ required: !0, message: "请输入 Agent URL" }]
        },
        e.createElement(le, {
          placeholder: "https://agent.example.com"
        })
      ),
      e.createElement(
        pe.Item,
        { name: "alias", label: "别名" },
        e.createElement(le, { placeholder: "输入别名（可选）" })
      ),
      e.createElement(
        pe.Item,
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
      de === "gateway" ? e.createElement(
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
      de && de !== "gateway" ? e.createElement(
        pe.Item,
        { name: "auth_token", label: "认证凭证" },
        e.createElement(le.Password, {
          placeholder: "Bearer Token 或 API Key"
        })
      ) : null
    ), he = o ? e.createElement(
      "div",
      null,
      e.createElement(
        me,
        { column: 1, bordered: !0, size: "small" },
        e.createElement(
          me.Item,
          { label: "URL" },
          o.url
        ),
        e.createElement(
          me.Item,
          { label: "别名" },
          o.alias || "-"
        ),
        e.createElement(
          me.Item,
          { label: "Agent 名称" },
          o.name || "-"
        ),
        e.createElement(
          me.Item,
          { label: "状态" },
          e.createElement(et, {
            color: o.status === "connected" ? "#52c41a" : o.status === "error" ? "#ff4d4f" : "#d9d9d9",
            text: o.status === "connected" ? "已连接" : o.status === "error" ? "错误" : "未连接"
          })
        ),
        e.createElement(
          me.Item,
          { label: "认证类型" },
          o.auth_type ? e.createElement(
            H,
            { color: "blue" },
            {
              gateway: "阿里云Agent Hub",
              bearer: "Bearer Token",
              api_key: "API Key"
            }[o.auth_type] || o.auth_type
          ) : "无认证"
        ),
        e.createElement(
          me.Item,
          { label: "描述" },
          o.description || "-"
        ),
        e.createElement(
          me.Item,
          { label: "版本" },
          o.version || "-"
        )
      ),
      ((mt = o.skills) == null ? void 0 : mt.length) > 0 ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "技能"),
        ...o.skills.map(
          (l, E) => e.createElement(
            te,
            { key: E, size: "small", style: { marginBottom: 8 } },
            e.createElement("strong", null, l.name),
            l.description ? e.createElement(
              "div",
              { style: { color: "#666", fontSize: 12 } },
              l.description
            ) : null
          )
        )
      ) : null,
      o.capabilities ? e.createElement(
        "div",
        { style: { marginTop: 16 } },
        e.createElement("h4", null, "能力"),
        e.createElement(
          q,
          null,
          e.createElement(
            H,
            {
              color: o.capabilities.streaming ? "green" : "default"
            },
            "Streaming"
          ),
          e.createElement(
            H,
            {
              color: o.capabilities.push_notifications ? "green" : "default"
            },
            "Push Notifications"
          )
        )
      ) : null,
      o.error ? e.createElement(
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
        o.error
      ) : null,
      e.createElement(Ct, null),
      e.createElement(
        q,
        null,
        e.createElement(
          T,
          {
            type: "primary",
            icon: Me ? e.createElement(Me) : null,
            loading: V,
            onClick: h
          },
          "刷新 Agent Card"
        ),
        e.createElement(
          T,
          {
            danger: !0,
            icon: rt ? e.createElement(rt) : null,
            onClick: u
          },
          "删除"
        )
      )
    ) : null, R = e.createElement(
      kt,
      {
        title: S ? "注册远程 A2A Agent" : (o == null ? void 0 : o.name) || (o == null ? void 0 : o.alias) || "Agent 详情",
        open: s,
        onClose: _,
        width: 480,
        footer: S ? e.createElement(
          q,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(T, { onClick: _ }, "取消"),
          e.createElement(
            T,
            { type: "primary", loading: M, onClick: C },
            "注册"
          )
        ) : null
      },
      S ? ue : he
    ), oe = e.createElement(
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
          q,
          null,
          e.createElement(
            T,
            {
              icon: Me ? e.createElement(Me) : null,
              onClick: f,
              loading: i
            },
            "刷新列表"
          ),
          e.createElement(
            T,
            {
              icon: tt ? e.createElement(tt) : null,
              onClick: x
            },
            "从阿里云AgentHub导入"
          ),
          e.createElement(
            T,
            {
              type: "primary",
              icon: nt ? e.createElement(nt) : null,
              onClick: $
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
    ), Le = i ? e.createElement(
      "div",
      { style: { textAlign: "center", padding: 60 } },
      e.createElement(Ee, { size: "large" })
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
        (l) => e.createElement(It, {
          key: l.alias || l.url,
          agent: l,
          onClick: () => p(l)
        })
      )
    ), Se = k.length > 0, _e = Math.ceil(A.length / ye), dt = (G - 1) * ye, Bt = A.slice(dt, dt + ye), Nt = e.createElement(
      Ze,
      {
        title: Se ? "导入结果" : "从阿里云AgentHub导入 Agent",
        open: ae,
        onCancel: P,
        closable: !g || Se,
        maskClosable: !g || Se,
        width: 800,
        footer: Se ? e.createElement(
          q,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            T,
            { type: "primary", onClick: P },
            "关闭"
          )
        ) : A.length > 0 ? e.createElement(
          q,
          { style: { display: "flex", justifyContent: "flex-end" } },
          e.createElement(
            T,
            { onClick: P },
            "取消"
          ),
          e.createElement(
            T,
            {
              type: "primary",
              loading: g,
              disabled: m.size === 0,
              onClick: J
            },
            `确认导入 (${m.size}/${A.length})`
          )
        ) : null
      },
      // Loading state
      g && A.length === 0 && e.createElement(
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
        e.createElement(Ee, { size: "large" }),
        e.createElement(
          "span",
          { style: { fontSize: 13, color: t.colorTextTertiary } },
          "正在从 AgentHub 获取 Agent 列表..."
        )
      ),
      // Agent selection list
      !g && A.length > 0 && e.createElement(
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
            `共 ${A.length} 个 Agent，已选 ${m.size} 个`
          ),
          e.createElement(
            q,
            { size: 4 },
            e.createElement(
              T,
              {
                size: "small",
                type: "link",
                style: { padding: 0, height: "auto" },
                onClick: we
              },
              "全选"
            ),
            e.createElement(
              T,
              {
                size: "small",
                type: "link",
                style: { padding: 0, height: "auto" },
                onClick: L
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
          ...Bt.map((l, E) => {
            var Ae;
            const w = m.has(l.url);
            return e.createElement(
              "div",
              {
                key: E,
                style: {
                  display: "flex",
                  gap: 8,
                  padding: 10,
                  border: w ? `1px solid ${t.colorInfo}` : `1px solid ${t.colorBorderSecondary}`,
                  borderRadius: 6,
                  cursor: F.has(l.url) ? "default" : "pointer",
                  background: F.has(l.url) ? t.colorBgLayout : w ? t.colorInfoBg : t.colorBgContainer,
                  transition: "all 0.15s ease",
                  opacity: F.has(l.url) ? 0.7 : 1
                },
                onClick: () => {
                  F.has(l.url) || D(l.url);
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
                  l.name || l.url
                ),
                l.description ? e.createElement(
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
                  l.description
                ) : null,
                ((Ae = l.skills) == null ? void 0 : Ae.length) > 0 ? e.createElement(
                  "div",
                  { style: { marginTop: 4 } },
                  ...l.skills.slice(0, 3).map(
                    (be, Re) => e.createElement(
                      H,
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
                  l.skills.length > 3 ? e.createElement(
                    H,
                    { style: { fontSize: 10 } },
                    `+${l.skills.length - 3}`
                  ) : null
                ) : null
              ),
              F.has(l.url) ? e.createElement(
                H,
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
            T,
            {
              size: "small",
              disabled: G === 1,
              onClick: () => ge((l) => l - 1)
            },
            "上一页"
          ),
          e.createElement(
            "span",
            { style: { fontSize: 12, color: t.colorTextTertiary } },
            `${G} / ${_e}`
          ),
          e.createElement(
            T,
            {
              size: "small",
              disabled: G === _e,
              onClick: () => ge((l) => l + 1)
            },
            "下一页"
          )
        )
      ),
      // Import results
      Se && e.createElement(
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
        ...k.map(
          (l, E) => e.createElement(
            "div",
            {
              key: E,
              style: {
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                borderRadius: 4,
                background: l.success ? t.colorInfoBg : t.colorErrorBg,
                border: l.success ? `1px solid ${t.colorInfo}` : `1px solid ${t.colorErrorBorder}`,
                fontSize: 12
              }
            },
            e.createElement(
              "span",
              {
                style: {
                  color: l.success ? t.colorSuccess : t.colorError,
                  fontSize: 14
                }
              },
              l.success ? "✓" : "✗"
            ),
            e.createElement(
              "span",
              {
                style: {
                  flex: 1,
                  color: l.success ? t.colorText : t.colorError
                }
              },
              l.name,
              l.error ? ` - ${l.error}` : ""
            )
          )
        )
      )
    );
    return e.createElement(
      "div",
      { style: { padding: 24 } },
      oe,
      Le,
      R,
      Nt
    );
  }
  function Rt({ data: t }) {
    var re, ye, F;
    const { token: n } = $e.useToken(), r = e.useRef(null), [a, i] = I({}), c = xe(() => {
      var f, $, p;
      const y = (p = ($ = (f = t == null ? void 0 : t.content) == null ? void 0 : f[0]) == null ? void 0 : $.data) == null ? void 0 : p.arguments;
      if (!y) return null;
      try {
        return JSON.parse(y);
      } catch {
        return null;
      }
    }, [(F = (ye = (re = t == null ? void 0 : t.content) == null ? void 0 : re[0]) == null ? void 0 : ye.data) == null ? void 0 : F.arguments]), { toolResult: s, rawErrorText: d } = xe(() => {
      var f;
      const y = t == null ? void 0 : t.content;
      if (!Array.isArray(y))
        return { toolResult: null, rawErrorText: "" };
      for (const $ of y) {
        const p = (f = $ == null ? void 0 : $.data) == null ? void 0 : f.output;
        if (!p) continue;
        let _ = "";
        if (Array.isArray(p)) {
          const C = p.find(
            (u) => (u == null ? void 0 : u.type) === "text" && (u == null ? void 0 : u.text)
          );
          _ = (C == null ? void 0 : C.text) || "";
        } else if (typeof p == "string")
          try {
            const C = JSON.parse(p);
            if (typeof C == "object" && (C != null && C.steps || C != null && C.response_text))
              return { toolResult: C, rawErrorText: "" };
            if (Array.isArray(C)) {
              const u = C.find((h) => (h == null ? void 0 : h.type) === "text" && (h == null ? void 0 : h.text));
              u != null && u.text && (_ = u.text);
            }
          } catch {
            _ = p;
          }
        if (_)
          try {
            return { toolResult: JSON.parse(_), rawErrorText: "" };
          } catch {
            return { toolResult: null, rawErrorText: _ };
          }
      }
      return { toolResult: null, rawErrorText: "" };
    }, [t == null ? void 0 : t.content]), o = (s == null ? void 0 : s.steps) || [], z = (s == null ? void 0 : s.task_state) || "", S = (s == null ? void 0 : s.error) || "", N = (s == null ? void 0 : s.response_text) || "";
    e.useEffect(() => {
      r.current && (r.current.scrollTop = r.current.scrollHeight);
    }, [o.length, N, d]), e.useEffect(() => {
      const y = { ...a };
      let f = !1;
      o.forEach(($, p) => {
        a[p] === void 0 && ($.type === "thinking" && $.done || $.type === "tool_call" && $.status !== "running") && (y[p] = !0, f = !0);
      }), f && i(y);
    }, [o]);
    const M = (c == null ? void 0 : c.agent_alias) || "", Q = (c == null ? void 0 : c.agent_url) || "", V = M || Q || "远程 Agent", v = {
      completed: { color: "#52c41a", text: "已完成" },
      TASK_STATE_COMPLETED: { color: "#52c41a", text: "已完成" },
      failed: { color: "#ff4d4f", text: "失败" },
      TASK_STATE_FAILED: { color: "#ff4d4f", text: "失败" },
      error: { color: "#ff4d4f", text: "出错" },
      canceled: { color: "#faad14", text: "已取消" },
      TASK_STATE_CANCELED: { color: "#faad14", text: "已取消" },
      AWAITING_USER_INPUT: { color: "#1677ff", text: "等待输入" },
      input_required: { color: "#1677ff", text: "等待输入" }
    }, B = (s !== null || !!d) && !(z === "working" || z === "TASK_STATE_WORKING");
    let g = "#1677ff", W = "执行中...";
    B && (v[z] ? (g = v[z].color, W = v[z].text) : d ? (g = "#ff4d4f", W = "出错") : (g = "#52c41a", W = "已完成"));
    const A = e.createElement(
      q,
      { size: 6 },
      e.createElement("span", { style: { fontSize: 13 } }, "🔗"),
      e.createElement(
        ne,
        { style: { fontSize: 12, color: "#595959" } },
        `A2A: ${V}`
      ),
      e.createElement(
        H,
        { color: g, style: { fontSize: 11, lineHeight: "18px" } },
        W
      )
    ), ie = o.length === 0 && !d && !S, m = !B && ie ? e.createElement(
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
      e.createElement(Ee, { size: "small" }),
      e.createElement(
        ne,
        { style: { fontSize: 12, color: "#52c41a" } },
        `正在连接 ${V}...`
      )
    ) : null;
    function b(y) {
      i((f) => ({
        ...f,
        [y]: !f[y]
      }));
    }
    function k(y, f) {
      const $ = !!a[f];
      if (y.type === "thinking") {
        const p = !!y.done, _ = p ? "💭" : "🧠", C = p ? "思考完成" : "思考中...", u = e.createElement(
          "div",
          {
            key: `step-${f}`,
            style: {
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: p ? "pointer" : "default",
              fontSize: 12,
              color: "#8c8c8c"
            },
            onClick: p ? () => b(f) : void 0
          },
          p && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            $ ? "▶" : "▼"
          ),
          e.createElement("span", null, _),
          e.createElement("span", null, C),
          !p && e.createElement(Ee, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return $ ? u : e.createElement(
          "div",
          { key: `step-${f}` },
          u,
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
        const p = y.status === "running", _ = y.status === "error", C = p ? "⚙️" : _ ? "❌" : "✅", u = p ? `正在执行: ${y.name}` : _ ? `执行失败: ${y.name}` : `执行完成: ${y.name}`, h = p ? "#1677ff" : _ ? "#ff4d4f" : "#52c41a", x = e.createElement(
          "div",
          {
            key: `step-${f}`,
            style: {
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "3px 0",
              cursor: p ? "default" : "pointer",
              fontSize: 12,
              color: h
            },
            onClick: p ? void 0 : () => b(f)
          },
          !p && e.createElement(
            "span",
            { style: { fontSize: 10, color: "#bfbfbf" } },
            $ ? "▶" : "▼"
          ),
          e.createElement("span", null, C),
          e.createElement("span", null, u),
          p && e.createElement(Ee, {
            size: "small",
            style: { marginLeft: 4 }
          })
        );
        return $ || !y.desc && !p ? x : e.createElement(
          "div",
          { key: `step-${f}` },
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
          key: `step-${f}`,
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
    const U = o.length > 0 ? e.createElement(
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
      ...o.map(k)
    ) : null, G = d || S ? e.createElement(
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
      S ? `错误: ${S}` : d
    ) : null, ge = !o.length && N && !d ? e.createElement(
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
        ne,
        {
          style: {
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: "1.6"
          }
        },
        N
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
      e.createElement("div", { style: { marginBottom: 6 } }, A),
      m,
      U,
      ge,
      G
    );
  }
  const zt = "__A2A_STREAM_START__", $t = "A2A_STREAM_START", ve = /* @__PURE__ */ new Set();
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
      const r = n.currentNode, a = r.nodeType === Node.TEXT_NODE ? r.textContent : r.innerHTML;
      if (je(a)) {
        const i = r.nodeType === Node.TEXT_NODE ? r.parentElement : r;
        if (i) return i;
      }
    }
    return null;
  }
  async function Ue(t) {
    var o, z;
    const n = window.QwenPaw;
    if (!(n != null && n.host)) {
      console.warn("[a2a] QwenPaw.host not available");
      return;
    }
    const { getApiUrl: r, getApiToken: a } = n.host, i = r("/a2a/call/stream"), c = a();
    console.log("[a2a] Subscribing to SSE stream:", i);
    const s = document.createElement("div");
    s.style.cssText = "background:#f6ffed;border:1px solid #b7eb8f;border-radius:8px;padding:12px 16px;margin:4px 0;font-size:13px;white-space:pre-wrap;word-break:break-word;color:#262626;min-height:24px;", s.textContent = "正在连接远程 Agent...", t.textContent = "", t.appendChild(s);
    const d = new AbortController();
    try {
      const S = {
        Accept: "text/event-stream"
      };
      c && (S.Authorization = `Bearer ${c}`);
      try {
        const v = sessionStorage.getItem("qwenpaw-agent-storage") || localStorage.getItem("qwenpaw-agent-storage"), O = (z = (o = JSON.parse(v || "{}")) == null ? void 0 : o.state) == null ? void 0 : z.selectedAgent;
        O && (S["X-Agent-Id"] = O);
      } catch {
      }
      console.log("[a2a] Fetching SSE with headers:", S);
      const N = await fetch(i, { headers: S, signal: d.signal });
      if (console.log("[a2a] SSE response status:", N.status), !N.ok) {
        const v = await N.text().catch(() => "");
        s.textContent = `SSE 连接失败 (${N.status}): ${v.slice(
          0,
          100
        )}`, s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0";
        return;
      }
      if (!N.body) {
        s.textContent = "SSE 连接失败：无响应体", s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0";
        return;
      }
      const M = N.body.getReader(), Q = new TextDecoder();
      let V = "";
      for (; ; ) {
        const { done: v, value: O } = await M.read();
        if (v) {
          console.log("[a2a] SSE stream ended (done)");
          break;
        }
        V += Q.decode(O, { stream: !0 });
        const ae = V.split(`
`);
        V = ae.pop() || "";
        for (const B of ae)
          if (B.startsWith("data: "))
            try {
              const g = JSON.parse(B.slice(6));
              if (console.log("[a2a] SSE event:", g), g.done) {
                g.error && (s.textContent = `错误: ${g.error}`, s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0"), console.log("[a2a] SSE done signal received");
                return;
              }
              typeof g.response_text == "string" && g.response_text && (s.textContent = g.response_text);
            } catch (g) {
              console.warn("[a2a] SSE parse error:", g, "line:", B);
            }
      }
    } catch (S) {
      (S == null ? void 0 : S.name) !== "AbortError" && (console.error("[a2a] SSE subscription error:", S), s.textContent = `连接出错: ${(S == null ? void 0 : S.message) || S}`, s.style.borderColor = "#ff4d4f", s.style.background = "#fff1f0");
    }
  }
  function Ot() {
    console.log("[a2a] Initializing stream interceptor");
    function t(i) {
      if (i.nodeType !== Node.ELEMENT_NODE) return;
      const c = i, s = We(c);
      if (s && ve.has(s)) return;
      const d = Pt(c);
      d && (console.log("[a2a] Marker detected in DOM, msgId:", s), s && ve.add(s), Ue(d));
    }
    new MutationObserver((i) => {
      for (const c of i) {
        for (const s of c.addedNodes)
          t(s);
        c.target.nodeType === Node.ELEMENT_NODE && t(c.target);
      }
    }).observe(document.body, {
      childList: !0,
      subtree: !0,
      characterData: !0,
      characterDataOldValue: !0
    });
    const r = setInterval(() => {
      const i = document.evaluate(
        "//text()[contains(., 'A2A_STREAM_START')]",
        document.body,
        null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
        null
      );
      for (let c = 0; c < i.snapshotLength; c++) {
        const d = i.snapshotItem(c).parentElement;
        if (d) {
          const o = We(d);
          if (o && ve.has(o)) continue;
          console.log("[a2a] Marker found in periodic scan, msgId:", o), o && ve.add(o), Ue(d);
        }
      }
    }, 500);
    window.addEventListener("beforeunload", () => clearInterval(r));
    const a = document.evaluate(
      "//text()[contains(., 'A2A_STREAM_START')]",
      document.body,
      null,
      XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
      null
    );
    for (let i = 0; i < a.snapshotLength; i++) {
      const s = a.snapshotItem(i).parentElement;
      if (s) {
        const d = We(s);
        d && ve.add(d), console.log("[a2a] Marker found in existing DOM, msgId:", d), Ue(s);
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
  const e = "qwenpaw-last-used-agent", Y = "qwenpaw-agent-storage", Z = "cloudpaw-first-install", ee = "cloud-orchestrator";
  if (localStorage.getItem(Z)) return;
  localStorage.setItem(Z, "true");
  function X() {
    localStorage.setItem(e, ee);
    try {
      const te = localStorage.getItem(Y);
      if (te) {
        const K = JSON.parse(te);
        K.state = K.state || {}, K.state.selectedAgent = ee, localStorage.setItem(Y, JSON.stringify(K));
      } else
        localStorage.setItem(
          Y,
          JSON.stringify({
            version: 0,
            state: {
              selectedAgent: ee,
              agents: [],
              lastChatIdByAgent: {}
            }
          })
        );
    } catch {
    }
    try {
      const te = sessionStorage.getItem(Y);
      if (te) {
        const K = JSON.parse(te);
        K.state = K.state || {}, K.state.selectedAgent = ee, sessionStorage.setItem(Y, JSON.stringify(K));
      } else
        sessionStorage.setItem(
          Y,
          JSON.stringify({
            version: 0,
            state: {
              selectedAgent: ee,
              agents: [],
              lastChatIdByAgent: {}
            }
          })
        );
    } catch {
    }
  }
  X(), window.addEventListener(
    "beforeunload",
    () => {
      X();
    },
    { once: !0 }
  ), console.info(
    "[cloudpaw] Set default agent to cloud-orchestrator for first-time user"
  ), window.location.reload();
}
function Ht() {
  var q;
  const e = (q = window.QwenPaw) == null ? void 0 : q.modules;
  if (!e) return;
  const Y = e["Chat/OptionsPanel/defaultConfig"];
  if (!(Y != null && Y.configProvider)) {
    console.warn(
      "[cloudpaw] configProvider not found — skipping welcome/theme patch"
    );
    return;
  }
  const Z = Y.configProvider, ee = Z.getConfig.bind(Z), X = "https://gw.alicdn.com/imgextra/i2/O1CN01pyXzjQ1EL1PuZMlSd_!!6000000000334-2-tps-288-288.png", te = {
    zh: "CloudPaw 插件提示",
    en: "CloudPaw Plugin Tips",
    ja: "CloudPaw プラグインのヒント",
    ru: "Подсказки плагина CloudPaw"
  }, K = {
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
  }, H = {
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
    const T = localStorage.getItem("language") || "";
    return T ? T.split("-")[0] : (navigator.language || "").split("-")[0] || "en";
  }
  if (Z.getGreeting = () => te[ke()] || te.en, Z.getDescription = () => K[ke()] || K.en, Z.getPrompts = () => H[ke()] || H.en, Z.getConfig = function(T) {
    var Te;
    const le = ee(T);
    return {
      ...le,
      theme: {
        ...le.theme,
        leftHeader: {
          ...(Te = le.theme) == null ? void 0 : Te.leftHeader,
          title: "Work with CloudPaw"
        }
      },
      welcome: {
        ...le.welcome,
        avatar: X
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
Dt();
