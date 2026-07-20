import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Tag } from "antd";
import { PageHeader } from "@/components/PageHeader";
import { useAppMessage } from "@/hooks/useAppMessage";
import { Slot } from "@/plugins/registry/Slot";
import { installPlugin } from "@/api/modules/plugin";
import styles from "./index.module.less";

const LOCAL_CREATOR_SOURCE = "qwenpaw-source://app/qwenpaw-creator";

function CreatorIntroduction() {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    setError(null);
    try {
      await installPlugin(LOCAL_CREATOR_SOURCE);
      message.success(t("creator.installSuccess"));
      window.location.reload();
    } catch (err) {
      const detail =
        err instanceof Error ? err.message : t("creator.installFailed");
      setError(detail);
      message.error(detail);
      setInstalling(false);
    }
  }, [message, t]);

  return (
    <div className={styles.content}>
      <PageHeader current={t("nav.creator", { defaultValue: "Creator" })} />
      <section className={styles.introduction}>
        <div className={styles.introCopy}>
          <Tag className={styles.badge} color="purple">
            {t("creator.badge")}
          </Tag>
          <h1>{t("creator.introTitle")}</h1>
          <p className={styles.description}>{t("creator.introDescription")}</p>

          <div className={styles.installPrompt}>
            <div className={styles.installMark} aria-hidden="true">
              C
            </div>
            <div className={styles.installCopy}>
              <strong>{t("creator.installTitle")}</strong>
              <span>{t("creator.installHint")}</span>
            </div>
            <Button
              className={styles.installButton}
              type="primary"
              size="large"
              disabled={installing}
              onClick={() => void handleInstall()}
            >
              {installing && (
                <span className={styles.installSpinner} aria-hidden="true" />
              )}
              <span>
                {t(
                  installing
                    ? "creator.installingAction"
                    : "creator.installAction",
                )}
              </span>
            </Button>
            {error && (
              <div className={styles.installError} role="alert">
                <span>{error}</span>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

export default function CreatorPage() {
  const defaultContent = <CreatorIntroduction />;

  return (
    <div className={styles.page}>
      <Slot name="creator.content" kind="replace">
        {defaultContent}
      </Slot>
    </div>
  );
}
