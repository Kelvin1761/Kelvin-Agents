# Dimension ML Promotion Recommendation

## Decision

**Do not promote to production.**

今次係個別維度 research audit，唔係 production 權重搜尋。即使有維度通過今輪窄門，亦只代表值得做 shadow candidate。

同時通過 development 與 external non-regression：沒有。

`stability` 已批准以固定 feature list、L2=1.0、cap=0.05 接入 opt-in shadow monitoring；主排名、Grade、verdict、Top Pick及投注建議保持不變。唔應因 9 場 external 或單一成功 swap 即時改 Matrix。
