# Tasks — Desktop Shell v1.5

> Spec: [09-spec-desktop-shell.md](09-spec-desktop-shell.md) · Plan:
> [dev/plans/2026-07-19-desktop-shell.md](dev/plans/2026-07-19-desktop-shell.md).
>
> File này chỉ theo dõi thực thi. Việc hoàn thiện spec/plan không đồng nghĩa tính năng
> đã được triển khai hoặc nghiệm thu.

**Trạng thái:** 🟢 xong · 🔵 đang làm · ⚪ chưa làm · ⛔ bị chặn

| # | Task | Trạng thái | Điều kiện hoàn tất |
|---|---|---|---|
| 0 | Chốt spec + implementation plan | 🟢 | Spec có acceptance IDs, plan có TDD/verify và self-review |
| 1 | Runtime state, single-instance, logging, tray lifecycle | ⚪ | Unit tests + DS-04/05/06/07/08/10 |
| 2 | Icon chung + macOS `.app` installer | ⚪ | Artifact thật + DS-01/02/03 trên Mac |
| 3 | Windows hidden launcher + Desktop/Start Menu shortcuts | ⚪ | Artifact thật + DS-01/02/03 trên Windows |
| 4 | Uninstaller Mac/Windows hai xác nhận | ⚪ | Fixture an toàn + DS-11/12/13 |
| 5 | README + ảnh Gatekeeper/SmartScreen + fallback | ⚪ | DS-16, không còn hướng dẫn daily bằng `run.*` |
| 6 | Nghiệm thu macOS + regression core | ⚪ | DS-01..15 phần Mac có bằng chứng mới |
| 7 | Nghiệm thu Windows thật | ⛔ | Cần máy Windows/VM tương đương để chạy DS-01..16 |
| 8 | Chốt release status | ⚪ | Tất cả tiêu chí bắt buộc PASS; tag chỉ khi người dùng cho phép |

## Preconditions

- [ ] Task 14 core v1 hoàn tất, **hoặc** người dùng cho phép rõ ràng triển khai shell
  trước khi nghiệm thu core xong.
- [ ] Worktree implementation không có thay đổi dở dang chồng lên các file Desktop
  Shell, hoặc các thay đổi đó đã được chủ sở hữu xử lý.
- [ ] Có kế hoạch tiếp cận máy Windows thật/VM cho Task 7.

## Kết quả nghiệm thu

| ID | Mac | Windows | Bằng chứng / ghi chú |
|---|---|---|---|
| DS-01 | — | — | |
| DS-02 | — | — | |
| DS-03 | — | — | |
| DS-04 | — | — | |
| DS-05 | — | — | |
| DS-06 | — | — | |
| DS-07 | — | — | |
| DS-08 | — | — | |
| DS-09 | — | — | |
| DS-10 | — | — | |
| DS-11 | — | — | |
| DS-12 | — | — | |
| DS-13 | — | — | |
| DS-14 | — | — | |
| DS-15 | — | — | |
| DS-16 | — | — | |

## Quy tắc cập nhật trạng thái

- Chỉ đánh 🟢 sau khi verify của task chạy mới và có output/evidence.
- Không suy ra Windows PASS từ macOS hoặc kiểm tra tĩnh.
- Không gắn tag trong plan này nếu chưa được người dùng cho phép rõ ràng.
- Mọi commit implementation dùng trailer:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

