# Đối chiếu tay `catalog-overrides.yaml`

File nằm ở `server/src/cloudy_labs/coverage/catalog-overrides.yaml`, không phải ở `registry/` như plan ghi. Lý do: loader registry đọc mọi `*.yaml` trong thư mục đó.

Đối chiếu ngày 2026-10-31 với tiêu đề và mục lục trong CSV danh mục. Chỉ ghi slug và lý do.

| Mục | Lab khớp | Kết quả |
|---|---|---|
| `ebs-snapshot` | lab-016-tao-snapshot-va-restore-ebs-volume, lab-017-copy-ebs-snapshot-sang-region-khac, lab-020-thiet-ke-ebs-backup-monitoring-va-cost-control, lab-24-tao-ebs-snapshot-va-restore-volume-o-availability-zone-khac, lab-25-bat-ebs-fast-snapshot-restore-cho-kiem-thu-dr | Đúng cả 5: lab tạo hoặc khôi phục snapshot EBS. |
| `codecommit` | lab-129-…-codecommit-…, lab-25-quan-ly-ma-nguon-…-codecommit-…, lab-46-…-codecommit-…, lab-83-…-codecommit | Đúng cả 4: lab dùng repo CodeCommit. |
| `dhcp-options` | (không lab nào) | Giữ lại. Mục lục không nêu, nhưng trang lab có thể gọi `CreateDhcpOptions`; chế độ một lab bắt được qua lệnh. |
| `egress-only-internet-gateway` | lab-033-egress-only-internet-gateway | Đúng. lab-015-private-route-qua-nat-gateway có cụm "Egress-Only" nhưng nói về NAT; từ khoá là cả cụm "Egress-Only Internet Gateway" nên không khớp nhầm. |
| `placement-group` | lab-091-do-latency-giua-az, lab-11-dung-cluster-placement-group-…, lab-12-dung-spread-hoac-partition-placement-group-… | Đúng cả 3: lab tạo placement group. |
| `rds-oracle` | lab-002-so-sanh-mysql-postgresql-mariadb-oracle-va-sql-server, lab-007-db-option-group, lab-025-danh-gia-rds-oracle | Đúng cả 3: lab tạo instance Oracle (lab-007 dùng option group của Oracle). Với lệnh, mục này chỉ khớp khi có `--engine oracle…`. |
| `rds-sql-server` | lab-002-…, lab-007-db-option-group, lab-024-tao-rds-sql-server | Đúng cả 3. Mục này thêm ngoài danh sách khởi đầu của plan, vì Floci cũng không chạy engine SQL Server. |
| `rds-sql-server` (loại trừ) | lab-042-tao-aurora-postgresql-cluster | Khớp nhầm: lab nói về Babelfish cho client SQL Server, còn engine là Aurora PostgreSQL. Ghi trong `exclude`. |
| `rds-blue-green` | lab-077-rds-blue-green-deployment | Đúng. Bảng action RDS của Floci 2.3.0 không có `CreateBlueGreenDeployment`. Mục thêm khi chạy coverage sau đợt 1. |
| `replace-root-volume` | lab-019-khoi-phuc-ec2-tu-snapshot-khi-volume-hong | Đúng. Bảng action EC2 của Floci 2.3.0 không có `CreateReplaceRootVolumeTask`. Mục thêm khi chạy coverage sau đợt 1. |
