# Course Assistant: CFG và procedural semantics

Đây là phiên bản thử nghiệm Course Assistant độc lập theo hướng Classical NLP.
Mã nguồn nằm trong `experiments/slide_pipeline`; dữ liệu mẫu và chú giải cần
thiết để chạy được đặt trong `data/`. Phần đóng góp của các thành viên vẫn
cần nhóm tự điền khi nộp bài.

## Kiến trúc và liên hệ với nội dung học

```text
Câu hỏi → CFG + chart parser → cây
→ logical form → xử lý tham chiếu theo context
→ thủ tục truy vấn → KB dạng fact có nguồn → câu trả lời
```

- Chapter 3: `grammar.cfg` khai báo văn phạm CFG; `syntax.py` dùng NLTK
  `CFG` và `ChartParser`. `generation.py` sinh câu từ cùng văn phạm.
- Chapter 7: `logic.py` tạo logical form dạng cấu trúc với biến, vị từ,
  `WH`, `YES_NO`, `AND`, `OR`; tham chiếu được giữ đến bước resolve.
- Chapter 10: các loại câu và thành phần được thiết kế cho miền môn học;
  đây là semantic grammar theo phạm vi ứng dụng, không phải bộ phân tích
  cú pháp tiếng Việt tổng quát.
- Chapter 11: `procedure.py` ánh xạ predicate LF sang quan hệ KB và chuyển
  WH/YES_NO sang `RETRIEVE`/`TEST`, EACH sang `ITERATE`, EVERY sang
  `CHECK_ALL`, THE sang `FIND_THE`; các phép nối dùng chung biến. Đây là
  hiện thực giới hạn theo miền, không phải bộ suy luận FOPC tổng quát.

Ví dụ `Mỗi chương nói về CFG học tuần nào?` tạo LF với miền xác định là
các chương nói về CFG. Predicate `DISCUSSES` được ánh xạ sang `HAS_TOPIC`,
`TAUGHT_IN` sang `SCHEDULED_IN`; `ITERATE` tìm tuần của từng chương và
giữ nguồn. `EVERY` chỉ kết luận trên các đối tượng tìm được trong KB và
trả `UNKNOWN` nếu không đủ thông tin; `THE` yêu cầu đúng một đối tượng
trong KB. Tính duy nhất và tính đầy đủ ở đây chỉ xét trên KB hiện có.

Với nhóm câu chương–chủ đề, `logic.py` kết hợp nghĩa của các constituent:
`TOPIC` tạo một chủ đề, `TOPIC_EXPR` kết hợp một hoặc hai chủ đề bằng
AND/OR, rồi áp dụng điều kiện đó cho chương cần tìm. Câu hỏi về tuần học
tái sử dụng cùng cách kết hợp. `semantic.txt` ghi thêm `semantic_composition`
để minh họa các bước này; những nhóm câu khác hiện vẫn được xử lý theo luật
của loại câu và không có trace đầy đủ cho từng constituent. Đây là cách hiện
thực compositionality giới hạn bằng các cấu trúc Python, không phải bộ lambda
calculus hay feature unification tổng quát.

## Cài đặt và chạy bằng Windows PowerShell

Mở PowerShell tại root repository `SampleNLP`, tạo môi trường Python nếu chưa có:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r experiments/slide_pipeline/requirements.txt
.\.venv\Scripts\python.exe -m experiments.slide_pipeline --demo
```

Một câu hỏi hoặc nhiều lượt trong cùng phiên:

```powershell
.\.venv\Scripts\python.exe -m experiments.slide_pipeline --question 'Chương nào nói về CFG?'

.\.venv\Scripts\python.exe -m experiments.slide_pipeline `
  --question 'Tuần 3 học gì?' `
  --question 'Chương này nói về gì?'
```

Mỗi lượt in cây, logical form, logical form sau resolve, intent/entity,
query form, dữ liệu truy xuất có nguồn, câu trả lời và context. Một lỗi
khớp văn phạm không đủ chứng minh câu hỏi ngoài miền; chương trình báo
không nhận diện được thay vì tự tạo câu trả lời.

Intent/entity được trích xuất từ cây và LF; query được dịch trực tiếp từ LF
đã resolve, không dùng intent/entity làm đầu vào riêng. COUNT đếm giá trị
trong KB và không kết luận là 0 khi thiếu fact. Các mục `optional_or_extension`
được ghi rõ là tùy chọn khi hỏi riêng phần đó, không nhập vào yêu cầu bắt buộc.

## Xuất đầu ra của BTL

```powershell
.\.venv\Scripts\python.exe -m experiments.slide_pipeline --export
```

Lệnh đọc `input/sentences.txt` của bản này và xuất **chỉ trong**
`experiments/slide_pipeline/output/`:

`grammar.txt`, `samples.txt`, `parse-results.txt`, `semantic.txt`,
`intent-entity.txt`, `query.txt`, `retrieval.txt`, `answer.txt`,
`dialogue.txt`, `evaluation.txt`, `evaluation-results.json` và
`sample-intent-audit.json`, `faq-audit.json`, `audit-results.json`. Tệp câu sinh tối đa 10.000 câu; mặc định xuất
500 câu khác nhau. Các tệp JSON lines ghi rõ câu hỏi tương ứng; cây không
thuộc văn phạm được xuất `()`.

## Đánh giá và kiểm tra

```powershell
.\.venv\Scripts\python.exe -m pytest experiments/slide_pipeline/tests -q
```

`evaluation_cases.json` xác định case, căn cứ và các tiêu chí mong đợi.
`evaluation.txt` ghi số case, số đạt các tiêu chí, tỷ lệ và những case
chưa đạt. Mỗi kết quả FOUND được kiểm tra có nguồn và các giá trị xuất hiện
trong câu trả lời; một số tiêu chí dùng giá trị bắt buộc thay vì so sánh toàn bộ
câu trả lời, nên đây là **tỷ lệ đạt tiêu chí**, không phải phép đo đầy đủ
độ đúng của mọi fact. Các case được dùng trong phát triển, không phải tập
đánh giá độc lập; không suy rộng tỷ lệ này ra câu hỏi chưa được kiểm tra.

`audit_cases.json` là bộ khảo sát bổ sung do cùng nhóm phát triển tạo, không
phải tập độc lập. `audit-results.json` và `evaluation.txt` ghi riêng từng
case chưa đạt để phân tích; không coi tỷ lệ đạt tiêu chí là accuracy đáp án.

Chương trình còn so intent với nhãn Q001–Q028 của `sample_queries.txt`;
phép so này chỉ đo intent, không đo entity, truy xuất hoặc câu trả lời.
Với FAQ, chương trình chỉ khảo sát văn phạm nhận được câu hay không và
trạng thái truy xuất, không coi `FOUND` là đã chấm đúng câu trả lời.
Các case hội thoại được đánh giá riêng theo nhiều lượt.

## Dữ liệu, quan hệ và nguồn

KB độc lập đọc `course_info.txt`, `schedule.txt`, `topics.txt`,
`assignments.txt`, `regulations.txt`, `resources.txt` và chú giải nhóm
`data/annotations/resource_topics.yaml`. Ngoài ra, chú giải thử nghiệm
`annotations/relations.yaml` ghi rõ từng cặp, căn cứ và liên kết tài liệu;
các cặp này cần nhóm kiểm tra trước khi áp dụng chung. Các fact giữ nguồn tới bản ghi;
fact resource–topic từ chú giải được ghi nguồn chú giải riêng, không ghi
nhầm là quan hệ nguyên gốc.

Quan hệ `HAS_TOPIC` được suy ra bằng cách đối chiếu các từ khóa và một số
cụm chủ đề trong mục con, kể cả alias `QA` → `QUESTION ANSWERING`. Đây
là quy tắc khớp từ có căn cứ từ tài liệu, không hiểu toàn bộ ngữ nghĩa văn
bản. `và` giữa hai topic được chọn là AND, `hoặc` là OR; đây là quy ước
riêng cần nhóm xem xét trước khi dùng làm contract chung.

Câu hỏi tài liệu theo chương tìm chủ đề chung qua `HAS_TOPIC` và `RESOURCE_TOPIC`;
đây là tài liệu liên quan theo chủ đề, không phải danh sách giảng viên chỉ định.
Quan hệ LO4.2–CH12 là đối chiếu thử nghiệm, không phải ánh xạ chính thức.
Những quan hệ chưa có căn cứ, deadline hay giảng viên thiếu dữ liệu trả `NOT_FOUND`. Với câu
Có/Không, chỉ trả `False` khi có bằng chứng phủ định tường minh; không tìm
thấy fact dương mà cũng không có fact phủ định thì trả `UNKNOWN`.

## Docker (tùy chọn)

Chạy từ root repository để Docker có quyền đọc dữ liệu nguồn:

```powershell
docker build -f experiments/slide_pipeline/Dockerfile -t nlp-slide-assistant .
docker run --rm nlp-slide-assistant --demo
```

## Giới hạn hiện tại

- Các nhóm truy vấn chính của đề đã có luật đại diện, nhưng văn phạm chưa
  bao phủ mọi cách diễn đạt tiếng Việt; xem case chưa đạt trong evaluation.
- `TOPIC` và các mẫu từ vựng được giới hạn trong grammar; `NUMBER`, mã phần
  BTL và LO được nhận diện trước như token từ vựng, sau đó dựng lại lá cây.
- LF hỗ trợ WH/Yes–No/AND/OR và các mẫu EACH/EVERY/THE về chương–tuần;
  chưa hỗ trợ phủ định tổng quát, lồng lượng từ, suy luận logic tổng quát
  hay mọi tham chiếu. Ánh xạ predicate hiện chỉ áp dụng cho một số quan hệ.
- Không tự khẳng định “không” từ dữ liệu thiếu; đầu ra cần người dùng hiểu
  khi hệ thống chỉ biết thông tin trong bộ dữ liệu được cung cấp.
- Chưa tích hợp vào production, chưa thay shared contract, chưa khẳng định
  toàn bộ đầu ra hay mọi yêu cầu nộp bài của nhóm đã hoàn thành; báo cáo,
  video demo và thông tin thành viên vẫn cần nhóm chuẩn bị.

## Mã nguồn

`grammar.cfg`, `syntax.py`, `generation.py`: văn phạm, parser và sinh câu.
`logic.py`: logical form. `procedure.py`: resolve, query và thực thi.
`knowledge.py`: fact có nguồn. `assistant.py`, `__main__.py`: pipeline và
CLI. `exporter.py`, `evaluation.py`, `evaluation_cases.json`, `tests/`:
đầu ra và kiểm tra.
