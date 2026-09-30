# Kiem tra tai lieu tham khao

Ngay kiem tra: 2026-09-29. Thu tu duoi day la thu tu xuat hien [1]-[24] trong `main.pdf`.

| Ref. | Khoa BibTeX | Ket qua metadata | Muc do ho tro citation |
|---:|---|---|---|
| [1] | `Galceran2013` | Co that; title, tac gia, tap, trang, nam va DOI dung | Truc tiep ho tro tong quan coverage path planning (CPP) cho robot |
| [2] | `Cabreira2019` | Co that; metadata va DOI dung | Truc tiep ho tro tong quan CPP cho UAV |
| [3] | `Fevgas2022` | Co that; metadata va DOI dung | Truc tiep ho tro CPP UAV theo huong tiet kiem nang luong va hop tac |
| [4] | `Choset2001` | Co that; metadata va DOI dung | Truc tiep ho tro cell decomposition va boustrophedon coverage |
| [5] | `Maza2007` | Co that; bo sung DOI cua chuong sach | Truc tiep ho tro polygon decomposition va cooperative coverage |
| [6] | `Avellar2015` | Co that; metadata va DOI dung | Truc tiep ho tro multi-UAV area coverage voi muc tieu thoi gian |
| [7] | `DiFranco2015` | Co that; bo sung DOI | Truc tiep ho tro energy-aware UAV coverage |
| [8] | `Gerkey2004` | Co that; metadata va DOI dung | Truc tiep ho tro taxonomy MRTA |
| [9] | `Dias2006` | Co that; metadata va DOI dung | Truc tiep ho tro market-based multi-robot coordination |
| [10] | `Choi2009` | Co that; metadata va DOI dung | Truc tiep ho tro consensus-based decentralized auction va tinh robust |
| [11] | `Brunet2008` | Co that; bo sung ten hoi nghi day du, ma bai va DOI | Truc tiep ho tro consensus-based auction |
| [12] | `Lemaire2004` | Co that; metadata va DOI dung | Truc tiep ho tro distributed task allocation trong multi-UAV |
| [13] | `Parker1998` | Co that; bo sung DOI | Truc tiep ho tro fault-tolerant multi-robot cooperation |
| [14] | `Barnawi2025` | Co that tren trang nha xuat ban; metadata va DOI dung | Truc tiep ho tro consensus/task reassignment cho degraded UAV fleet |
| [15] | `Zeng2026` | Co that tren IEEE; volume, issue, trang va DOI dung | Truc tiep ho tro bidirectional reallocation sau payload failure |
| [16] | `Giacomossi2026` | Co that; arXiv ghi accepted at MIPRO 2026 va proceedings liet ke bai | Truc tiep ho tro market-based replanning sau khi tac nhan bi loai; giu nhan `Accepted` vi chua xac nhan DOI proceedings |
| [17] | `Fiorini1998` | Co that; bo sung DOI | Truc tiep ho tro Velocity Obstacles |
| [18] | `vandenBerg2008` | Co that; bo sung DOI | Truc tiep ho tro Reciprocal Velocity Obstacles |
| [19] | `vandenBerg2011` | Co that; bo sung series, volume va DOI chuong sach | Ho tro reciprocal n-body collision avoidance; khong dung rieng de gan nhan ORCA |
| [20] | `Ferrera2018` | Co that; bo sung DOI | Truc tiep ho tro decentralized 3-D collision avoidance cho multi-UAV |
| [21] | `Huang2019` | Co that; bo sung DOI | Truc tiep ho tro distributed cooperative avoidance; cau trong bai da duoc viet rong, khong gan mot co che do cao cu the |
| [22] | `Meier2015` | Co that; bo sung DOI | Truc tiep ho tro kien truc PX4; API mission/telemetry duoc ho tro them boi [23] |
| [23] | `MAVSDK` | Tai lieu chinh thuc; cap nhat URL va ngay truy cap | Truc tiep ho tro su ton tai cua mission va telemetry API |
| [24] | `PX4Failsafe` | Tai lieu chinh thuc; doi sang URL failsafe va return cu the | Truc tiep ho tro cac hanh dong Hold/Return/Land; khoang trong tai phan bo cap doi bay la suy luan cua bai |

## Nguon chinh da doi chieu

- ScienceDirect/Elsevier: https://www.sciencedirect.com/science/article/abs/pii/S092188901300167X
- MDPI Drones: https://www.mdpi.com/2504-446X/3/1/4
- MDPI Sensors: https://www.mdpi.com/1424-8220/22/3/1235 va https://www.mdpi.com/1424-8220/15/11/27783
- SAGE IJRR: https://journals.sagepub.com/doi/10.1177/0278364904045564 va https://journals.sagepub.com/doi/10.1177/027836499801700706
- IEEE Xplore: https://ieeexplore.ieee.org/document/5072249 va https://ieeexplore.ieee.org/document/681242
- Springer: https://link.springer.com/book/10.1007/978-3-642-19457-3
- SCIEPublish: https://www.sciepublish.com/article/pii/699
- arXiv/MIPRO: https://arxiv.org/abs/2606.01970 va https://www.mipro-proceedings.com/en/dc-cps
- MAVSDK: https://mavsdk.mavlink.io/main/en/
- PX4: https://docs.px4.io/main/en/config/safety va https://docs.px4.io/main/en/flight_modes/return

## Ket luan audit

- Khong phat hien tai lieu bia dat trong 24 muc.
- Cac reference [14]-[16] ton tai va phu hop voi doan Related Work.
- [16] la truong hop can than trong nhat: co preprint va xac nhan accepted/listing tai MIPRO 2026, nhung chua gan thong tin trang hay DOI proceedings khi chua xac minh duoc tu proceedings record.
- Hai cau citation co nguy co qua muc trong `main.tex` da duoc sua: bo cach goi ORCA khong duoc [19] ho tro truc tiep, va danh dau khoang trong tai phan bo cap doi bay la suy luan tu pham vi tai lieu PX4.
