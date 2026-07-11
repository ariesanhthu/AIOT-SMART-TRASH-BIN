## **TÀI LIỆU ĐẶC TẢ YÊU CẦU** 

**Hệ thống thùng rác thông minh** _**Hỗ trợ giáo dục phân loại rác nhằm nâng cao ý thức cho học sinh**_ **Phiên bản 2.2** 

## **Chuẩn bị bởi nhóm 2** 

## **Thông tin thành viên:** 

|**Thông tin thành viên:**||
|---|---|
|Nguyễn Anh Thư (trưởng nhóm)|23127266|
|Trần Hoàng Nam|23127232|
|Nguyễn Phạm Minh Thư|23127307|
|Đặng Nguyễn Thành Hiếu|23127364|



**Môn học:** Nhập môn lập trình điều khiển thiết bị thông minh 

**GVHD:** TS. Võ Hoài Việt 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT **Vòng đời đặc tả yêu cầu** 

## **Lịch sử phiên bản và sửa đổi** 

|**Tác giả**|**Ngày**|**Lý do thay đổi**|**Giai đoạn**|**Phiên**<br>**bản**|
|---|---|---|---|---|
|Nguyễn Anh Thư|27/05/2026|-|Giai đoạn 1|0|
|Tất cả thành viên|29/05/2026|Bổ sung nội dung Giai<br>đoạn 1.|Giai đoạn 1|1|
|Đặng Nguyễn<br>Thành Hiếu|12/06/2026|Sửa mục tiêu 2, 3, sơ đồ<br>tổng quan hệ thống, cấu<br>trúc tài liệu và các sơ đồ<br>hành động.|Giai đoạn 1|1.1|
|Trần Hoàng Nam|12/06/2026|Sửa mục tiêu 1, sơ đồ use<br>case.|Giai đoạn 1|1.2|
|Nguyễn Anh Thư|12/06/2026|Sửa chính tả, chỉnh định<br>dạng.<br>Sửa bảng giá thiết bị, sơ<br>đồ kiến trúc, bối cảnh.<br>Bổ sung demo prototype.<br>Bổ sung phụ lục C.|Giai đoạn 1|1.3|
|Tất cả thành viên|13/06/2026|Bổ sung sơ đồ user flow|Giai đoạn 2|2.0|
|Đặng Nguyễn<br>Thành Hiếu<br>Trần Hoàng Nam|20/06/2026|Thêm use case cấu hình<br>và quản lý thiết bị từ xa<br>cho mục tiêu số 3.<br>Gôm các yêu cầu chức<br>năng 1, 2 và 5,8 lại cho<br>các mục tiêu 1, 2 và 3.<br>Làm rõ yêu cầu phi chức<br>năng 10.<br>Chỉnh sửa mục tiêu 2 và<br>trình bày use case 2 và<br>các yêu cầu kĩ thuật cho<br>mục tiêu 1 và 2 rõ ràng<br>hơn.|Giai đoạn 2|2.1|



Trang 2 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Tác giả**|**Ngày**|**Lý do thay đổi**|**Giai đoạn**|**Phiên**<br>**bản**|
|---|---|---|---|---|
|Nguyễn Anh Thư|30/06/2026|Chỉnh sửa lỗi tài liệu,<br>thay đổi từ ngữ.<br>Cập nhật trạng thái dự án.|Giai đoạn 2|2.2|



## **Phê duyệt tài liệu đặc tả yêu cầu:** 

|**Tên**|**Vai Trò**|**Tổ chức**|**Ngày**|
|---|---|---|---|
|Nguyễn Anh Thư|Trưởng nhóm|Trường Đại học Khoa học tự nhiên,<br>Đại học Quốc gia Thành phố Hồ<br>Chí Minh|30/05/2026|
|Nguyễn Anh Thư|Trưởng nhóm|Trường Đại học Khoa học tự nhiên,<br>Đại học Quốc gia Thành phố Hồ<br>Chí Minh|12/06/2026|
|Nguyễn Anh Thư|Trưởng nhóm|Trường Đại học Khoa học tự nhiên,<br>Đại học Quốc gia Thành phố Hồ<br>Chí Minh|30/06/2026|



Trang 3 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT **Lời cảm ơn** 

Tài liệu này được phát triển trong khuôn khổ dự án “ **Hệ thống thùng rác thông minh”** nhằm đặc tả các yêu cầu cho hệ thống thùng rác thông minh có khả năng nhận diện, phân loại rác và hỗ trợ giám sát vận hành trong môi trường trường học. Nhóm xin ghi nhận sự hướng dẫn của thầy Võ Hoài Việt và sự đóng góp của các thành viên trong quá trình xây dựng, phân tích và hoàn thiện tài liệu. 

Cấu trúc tài liệu có tham khảo từ mẫu đặc tả yêu cầu được cung cấp và đã được điều chỉnh phù hợp với phạm vi, mục tiêu và bối cảnh triển khai của dự án. Thông tin được tham khảo từ nhiều nguồn và có sử dụng công cụ ChatGPT hỗ trợ tìm kiếm và gợi ý thiết kế. 

Trang 4 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

## **Mục lục** 

Vòng đời đặc tả yêu cầu.............................................................................................................2 Lịch sử phiên bản và sửa đổi................................................................................................2 Lời cảm ơn........................................................................................................................... 4 Mục lục...................................................................................................................................... 5 1. Giới thiệu.....................................................................................................................................7 1.1 Mục đích và phạm vi tài liệu............................................................................................... 7 1.2 Bối cảnh............................................................................................................................... 7 1.3 Đối tượng người dùng..........................................................................................................9 1.4 Hướng dẫn sử dụng tài liệu..................................................................................................9 1.5 Định nghĩa, tiêu chuẩn và khung tổ chức.......................................................................... 10 1.5.1 Định nghĩa thuật ngữ.................................................................................................10 1.5.2 Tiêu chuẩn áp dụng................................................................................................... 10 1.5.3 Khung tổ chức yêu cầu..............................................................................................11 1.6 Phạm vi và định vị sản phẩm............................................................................................. 11 1.7 Các lớp kỹ thuật.................................................................................................................12 1.8 Các lớp người dùng, đặc điểm và quyền truy cập của người dùng....................................13 1.8.1 Quyền truy cập của người dùng cuối........................................................................ 13 1.8.2 Quyền truy cập của nhân viên vận hành....................................................................13 1.8.3 Quyền truy cập của quản trị viên hệ thống................................................................14 1.8.4 Truy cập AI và bảo trì............................................................................................... 14 1.9 Tài liệu Người dùng...........................................................................................................14 1.10 Ràng buộc thiết kế và triển khai...................................................................................... 15 1.10.1 Ràng buộc thiết kế...................................................................................................15 1.10.2 Ràng buộc triển khai................................................................................................15 1.11 Giả định và sự phù hợp với chính sách............................................................................15 1.11.1 Giả định................................................................................................................... 15 1.11.2 Sự phù hợp với chính sách nhà trường, quyền riêng tư và tính bền vững...............15 1.11.3 Chính sách cần phát triển........................................................................................ 15 2. Đề xuất giá trị, các kịch bản sử dụng và yêu cầu chức năng.....................................................17 2.1 Từ giá trị cốt lõi đến yêu cầu kỹ thuật hệ thống................................................................ 17 2.2 Mục đích và ranh giới hệ thống......................................................................................... 17 2.2.1 Mục đích....................................................................................................................17 2.2.2 Ranh giới hệ thống.................................................................................................... 18 2.3 MỤC TIÊU 1: Hệ thống tự động phân loại rác thành 3 nhóm (hữu cơ, giấy, nhựa) với độ chính xác ≥ 85% và thời gian phản hồi ≤ 5 giây trong điều kiện ánh sáng trong nhà.............21 2.3.1 Use Case: Đưa rác vào vùng chờ.............................................................................. 22 2.3.2 Use Case: Phân loại rác bằng Trí tuệ nhân tạo AI.....................................................23 2.3.3 Các yêu cầu chức năng kỹ thuật................................................................................24 2.4 MỤC TIÊU 2: Hệ thống tự động mở đúng ngăn tương ứng trong ≤ 5 giây sau khi nhận kết quả phân loại, sau khi đóng nắp ghi nhận tín hiệu cảm biến siêu âm và cập nhật trạng thái 

Trang 5 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

đèn trong ≤ 0.5 giây................................................................................................................. 25 2.4.1 Use Case: Điều khiển mở nắp ngăn chứa rác phù hợp..............................................26 2.4.2 Use Case: Giám sát lượng rác và cập nhật đèn tín hiệu............................................ 28 2.4.3 Các yêu cầu chức năng kỹ thuật................................................................................29 2.5 MỤC TIÊU 3: Dashboard nhận dữ liệu từ mạch chính qua Internet để cập nhật trạng thái thùng vừa ghi nhận rác trong ≤ 5 giây, hiển thị cảnh báo khi vượt ngưỡng đầy và lưu thống kê phân loại theo ngày tối thiểu 30 ngày................................................................................. 30 2.5.1 Use Case: Ghi nhận trạng thái lượng rác...................................................................31 2.5.2 Use Case: Thống kê phân loại rác.............................................................................32 2.5.3 Use Case: Xem dashboard trạng thái thùng.............................................................. 33 2.5.4 Use Case: Cấu hình và quản lý thiết bị từ xa............................................................ 34 2.5.5 Các yêu cầu chức năng kỹ thuật................................................................................35 3. Yêu cầu phi chức năng.............................................................................................................. 36 3.1 Yêu cầu chất lượng khi vận hành.......................................................................................36 3.1.1 Hiệu năng.................................................................................................................. 36 3.1.2 Lưu trữ dữ liệu...........................................................................................................36 3.1.3 Khả năng mở rộng.....................................................................................................37 3.1.4 Tính sẵn sàng và độ tin cậy....................................................................................... 37 3.1.5 Độ tin cậy của AI.......................................................................................................38 3.1.6 Bảo mật..................................................................................................................... 38 3.1.7 Quyền riêng tư...........................................................................................................39 3.2 Yêu cầu chất lượng ngoài vận hành...................................................................................39 3.2.1 Khả năng tiến hóa......................................................................................................39 3.2.2 Khả năng mở rộng tính năng.....................................................................................39 3.3 Danh sách yêu cầu phi chức năng......................................................................................40 4. Yêu cầu khác............................................................................................................................. 42 4.1 Dữ liệu mô tả tối thiểu thiết bị cần gửi lên hệ thống......................................................... 42 4.2 Các định dạng dữ liệu được hỗ trợ.....................................................................................43 5. Kết luận và kế hoạch phát triển tiếp theo.................................................................................. 45 Phụ lục A - Bảng giá thiết bị chi tiết............................................................................................. 50 Phụ lục B - PEAS và so sánh giải pháp.........................................................................................51 Phụ lục B.1 - PEAS..................................................................................................................51 Phụ lục B.2 - So sánh giải pháp...............................................................................................51 Phụ lục C - Thiết kế demo (prototype)..........................................................................................52 

Trang 6 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

## **1. Giới thiệu** 

## **1.1 Mục đích và phạm vi tài liệu** 

Tài liệu này cung cấp đặc tả yêu cầu đầy đủ cho dự án **“Thùng rác thông minh”** - một hệ thống phân loại rác tự động tích hợp thị giác máy tính với phần cứng điều khiển theo mô hình IoT. Tài liệu xác định những gì hệ thống cần thực hiện, các ràng buộc vận hành và các tiêu chí đo lường để đánh giá sự thành công của sản phẩm. Hệ thống kết hợp các thành phần cốt lõi sau thành một sản phẩm hoàn chỉnh: 

- Module camera AI thu thập hình ảnh và phân loại từng vật phẩm rác thành: hữu cơ, giấy, hoặc nhựa. Bộ điều khiển nhúng sử dụng ESP32-CAM. 

- Bộ điều khiển nhúng ESP32-CAM nhận kết quả phân loại từ mô hình AI và điều khiển động cơ servo để mở nắp đúng ngăn chứa rác tương ứng. Cảm biến siêu âm lắp phía trên mỗi ngăn để liên tục đo mức độ đầy của rác. 

- Giao diện phản hồi người dùng tại chỗ (đèn LED) truyền đạt trạng thái hoạt động của hệ thống đến người dùng. 

- Lớp cảnh báo và telemetry gửi thông báo lên hệ thống khi một ngăn đạt đến giới hạn chứa đầy hoặc thiết bị cần bảo trì. 

- Dashboard và API phục vụ giám sát từ xa, thống kê từng loại rác theo từng thùng và hỗ trợ tích điểm thưởng cho học sinh. 

## **Phạm vi tài liệu bao gồm:** 

- Thiết kế vật lý của thùng rác và cấu hình các ngăn (hữu cơ, giấy, nhựa). 

- Phần mềm điều khiển nhúng chạy trên ESP32-CAM. 

- Quy trình phân loại AI: suy luận mô hình, ngưỡng độ tin cậy và hành vi dự phòng. 

- Cơ chế phản hồi người dùng tại chỗ và logic cảnh báo vận hành. 

- Dữ liệu telemetry của thiết bị phục vụ giám sát, chẩn đoán và thống kê. 

- Kết nối Internet: thống kê số lượng từng loại rác tái chế theo từng thùng, phục vụ hệ thống tích điểm thưởng cho học sinh. 

## **Các nội dung nằm ngoài phạm vi của phiên bản này:** 

- Tối ưu hóa lộ trình thu gom rác cấp thành phố hoặc tích hợp với hạ tầng quản lý rác thải đô thị. 

- Nền tảng thương mại trao đổi phế liệu quy mô lớn. 

- Quy trình xử lý rác thải công nghiệp hoặc chất thải nguy hại. 

- Chứng nhận pháp lý hoặc tuân thủ quy định đối với các dòng rác thải. 

## **1.2 Bối cảnh** 

Tại Việt Nam, phân loại rác tại nguồn vẫn là một điểm nghẽn trong quá trình tái chế và quản lý rác thải. Theo bài viết của Reuters năm 2024[1] , dựa trên dữ liệu của Liên Hợp Quốc, Việt Nam nhập khoảng **420.000 tấn phế liệu nhựa trong năm 2023** , tăng 11% so với năm 2022. Tuy nhiên **chỉ khoảng 30% rác nhựa phát sinh tại Việt Nam được phân loại.** Điều này cho thấy 

1 Guarascio, F., & Vu, K. (2024, November 26). Top importer Vietnam struggles to recycle plastic waste, exposing limits of multibillion dollar trade. Reuters 

Trang 7 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

vấn đề không chỉ nằm ở lượng rác phát sinh, mà còn nằm ở chất lượng phân loại rác ngay từ đầu nguồn. 

Trong môi trường trường học, đặc biệt là ở bậc mầm non và tiểu học, việc phân loại rác vẫn phụ thuộc nhiều vào ý thức và khả năng nhận biết của từng học sinh. Học sinh nhỏ tuổi thường chưa có đủ kinh nghiệm để phân biệt chính xác các nhóm rác như nhựa, giấy và hữu cơ. Khi rác tái chế bị bỏ lẫn với rác hữu cơ hoặc rác không phù hợp, giá trị tái chế có thể bị giảm, đồng thời làm tăng gánh nặng kiểm tra, thu gom và vệ sinh cho nhân viên vận hành. 

Các chương trình giáo dục môi trường như **Eco-Schools** cho thấy việc nâng cao ý thức môi trường của học sinh cần được thực hiện thông qua hoạt động thực tế, có sự tham gia, theo dõi và lặp lại trong bối cảnh trường học. Một nghiên cứu bán thực nghiệm của Ozsoy, Ertepinar và Saglam trên 316 học sinh lớp 6, 7 và 8 cho thấy nhóm học sinh tham gia Eco-School[2] có kết quả cao hơn nhóm học sinh học theo phương pháp truyền thống ở các thang đo về kiến thức môi trường, thái độ, hành vi/sử dụng môi trường và mức độ quan tâm đến môi trường. Trong đó, điểm hành vi/sử dụng môi trường của nhóm Eco-School cao hơn nhóm đối chứng ở cả ba khối lớp. 

Từ bối cảnh trên, dự án Thùng rác thông minh AIoT được định vị không phải là giải pháp thay thế toàn bộ hệ thống xử lý và phân loại rác, mà là một thiết bị hỗ trợ giáo dục hành vi tại điểm bỏ rác. Hệ thống sử dụng camera và mô hình AI để nhận diện rác, điều khiển servo mở đúng ngăn chứa, đồng thời theo dõi mức đầy bằng cảm biến siêu âm và ghi nhận dữ liệu lên dashboard. Nhờ đó, học sinh nhận được phản hồi trực quan ngay khi bỏ rác, còn nhà trường có dữ liệu để theo dõi, nhắc nhở và tổ chức các hoạt động giáo dục hoặc thi đua về phân loại rác. 

Môi trường triển khai mục tiêu của sản phẩm mẫu là trường tiểu học và mẫu giáo, nơi việc hình thành thói quen phân loại rác từ sớm có ý nghĩa giáo dục lâu dài. Thông qua việc biến hành động bỏ rác hằng ngày thành một trải nghiệm học tập có phản hồi, hệ thống hướng đến mục tiêu góp phần nâng cao ý thức bảo vệ môi trường và giảm sai sót khi học sinh phân loại rác tại nguồn. 

## **Quy trình vận hành của hệ thống như sau:** 

- Người dùng đưa vật phẩm rác đến trước camera của thùng. 

- Camera thu thập hình ảnh và chuyển đến mô hình AI phân loại. 

- Mô hình AI phân loại vật phẩm thành: hữu cơ, giấy và nhựa - kèm nhãn lớp và điểm tin cậy. 

- ESP32-CAM nhận kết quả phân loại và điều khiển servo mở nắp đúng ngăn tương ứng. 

- Sau khi rác được bỏ vào, cơ cấu trở về trạng thái đóng mặc định. 

- Cảm biến siêu âm liên tục theo dõi mức độ đầy của từng ngăn; khi đạt ngưỡng, đèn LED cảnh báo sáng và hệ thống gửi thông báo lên dashboard vận hành. 

- Dữ liệu số lượng rác tái chế theo từng loại được ghi nhận và tổng hợp, phục vụ hệ thống tích điểm thưởng khuyến khích học sinh. 

> 2 [2] Ozsoy, S., Ertepinar, H., & Saglam, N. (2012). Can eco-schools improve elementary school students’ environmental literacy levels? Asia-Pacific Forum on Science Learning and Teaching, 13(2), Article 3. Nghiên cứu bán thực nghiệm trên 316 học sinh, gồm 156 học sinh nhóm Eco-School và 160 học sinh nhóm đối chứng. 

Trang 8 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

- Môi trường triển khai mục tiêu của sản phẩm mẫu là trường tiểu học và mẫu giáo - nơi mà việc xây dựng thói quen phân loại rác từ sớm có tác động giáo dục lâu dài và tích cực. 

## **1.3 Đối tượng người dùng** 

Tài liệu này được viết cho tất cả các bên liên quan đến thiết kế, phát triển, đánh giá, vận hành và bảo trì hệ thống Thùng Rác Thông Minh AIoT. 

_**Bảng 1: Đối tượng người dùng và nhu cầu chính**_ 

|**Nhóm**<br>**Vai trò**<br>**Nhu cầu chính**|**Nhóm**<br>**Vai trò**<br>**Nhu cầu chính**|**Nhóm**<br>**Vai trò**<br>**Nhu cầu chính**|
|---|---|---|
|Học sinh<br>(End user)|Người trực tiếp bỏ<br>rác vào thùng|Thao tác đơn giản, phản hồi dễ hiểu, không cần biết kỹ<br>thuật. Góp phần nâng cao nhận thức phân loại rác của<br>các em thông qua phản hồi trực quan và cơ chế tích<br>điểm thưởng.|
|Khách hàng<br>(Trường học)|Đơn vị mua và<br>triển khai thiết bị|Họ quan tâm đến hiệu quả vận hành, khả năng giám sát<br>từ xa và giá trị giáo dục mà sản phẩm mang lại cho học<br>sinh.|
|Nhân viên<br>vận hành|Đổ rác, vệ sinh, xử<br>lý cảnh báo|Biết đúng thùng/ngăn nào đầy, giảm kiểm tra thủ công.|
|Quản trị viên<br>hệ thống|Cấu hình thiết bị,<br>dashboard,<br>tài<br>khoản|Quản lý dữ liệu, cấu hình ngưỡng đầy và trạng thái thiết<br>bị.|
|Nhóm phát<br>triển|Thiết kế, lập trình,<br>kiểm thử prototype|Nhóm sinh viên phát triển sử dụng tài liệu này làm tài<br>liệu tham chiếu chính thức cho quá trình xây dựng sản<br>phẩm.<br>Giảng viên và hội đồng đánh giá sử dụng tài liệu để<br>kiểm tra xem sản phẩm mẫu có đáp ứng các yêu cầu và<br>tiêu chí nghiệm thu đề ra hay không.|



## **1.4 Hướng dẫn sử dụng tài liệu** 

Người đọc nên xem xét mục đích và ranh giới hệ thống trước, sau đó kiểm tra các trường hợp sử dụng (use cases) và yêu cầu chức năng (functional requirements) liên quan đến trách nhiệm của mình. Nhà phát triển phần cứng nên tập trung vào các ràng buộc về thiết bị, cảm biến, bộ chấp hành và nguồn điện. Nhà phát triển AI nên tập trung vào các yêu cầu về phân loại, ngưỡng độ tin cậy, thu thập dữ liệu và cập nhật mô hình. Nhà phát triển Backend nên tập trung vào các yêu cầu về telemetry, cảnh báo, API và định dạng dữ liệu. 

- Xác định môi trường triển khai dự kiến và chọn xem bản mẫu sử dụng một, hai, hay ba ngăn chứa rác. 

Trang 9 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

- Xem xét các cảm biến, bộ chấp hành và luồng điều khiển cần thiết trước khi tích hợp phần cứng. 

- Chọn các yêu cầu chức năng bắt buộc đối với bản mẫu đầu tiên và đánh dấu riêng các phần mở rộng trong tương lai. 

- Sử dụng các định danh yêu cầu khi kiểm thử, báo cáo lỗi hoặc ghi lại các sai lệch. 

## **1.5 Định nghĩa, tiêu chuẩn và khung tổ chức** 

Các định nghĩa, tiêu chuẩn và khung tổ chức dưới đây được sử dụng nhất quán trong toàn bộ tài liệu đặc tả, nhằm đảm bảo tính rõ ràng và khả năng kiểm thử của các yêu cầu. 

## **1.5.1 Định nghĩa thuật ngữ** 

_**Bảng 2: Định nghĩa thuật ngữ**_ 

|**Thuật ngữ**|**Định nghĩa**|
|---|---|
|AIoT|Trí tuệ nhân tạo kết hợp IoT (Artificial Intelligence of Things): hệ<br>thống trong đó các thiết bị kết nối thu thập dữ liệu và ứng dụng AI để<br>đưa ra quyết định cục bộ hoặc có sự hỗ trợ từ đám mây.|
|Smart Trash Bin|Thiết bị vật lý có khả năng tự động nhận diện, phân loại rác và điều<br>hướng rác vào đúng ngăn tương ứng.|
|Rác hữu cơ|Thức ăn thừa, lá cây và các vật liệu phân hủy sinh học có thể ủ compost<br>hoặc xử lý bằng phương pháp sinh học.|
|Mức độ đầy|Tỷ lệ phần trăm dung tích đã sử dụng của một ngăn chứa, được tính<br>toán dựa trên khoảng cách đo bởi cảm biến siêu âm.|
|Độ tin cậy phân loại|Điểm xác suất do mô hình AI trả về, thể hiện mức độ chắc chắn của kết<br>quả phân loại đối với một hạng mục rác.|
|Telemetry|Dữ liệu trạng thái có cấu trúc được thiết bị gửi lên hệ thống, bao gồm<br>giá trị cảm biến, kết quả phân loại, trạng thái lỗi và nhãn thời gian.|
|Tích điểm thưởng|Cơ chế ghi nhận điểm cho học sinh dựa trên số lần sử dụng thùng rác<br>đúng cách, phục vụ mục tiêu khuyến khích và giáo dục hành vi phân<br>loại rác.|



## **1.5.2 Tiêu chuẩn áp dụng** 

- Các yêu cầu được viết theo phong cách đặc tả yêu cầu phần mềm IEEE 830 có điều chỉnh cho phù hợp với quy mô dự án học thuật. 

- Dữ liệu telemetry của thiết bị sử dụng JSON làm định dạng trao đổi chính và ISO 8601 cho định dạng nhãn thời gian. 

- Giao tiếp với các dịch vụ bên ngoài nên sử dụng HTTPS hoặc MQTT over TLS khi kết nối mạng được kích hoạt. 

Trang 10 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

- Hệ thống tuân theo các thực hành an toàn nhúng phổ biến: cách ly nguồn điện, bảo vệ dòng servo, quản lý dây cáp và thiết kế vỏ hộp. 

- Dữ liệu hình ảnh phải được xử lý theo nguyên tắc privacy-by-design: ảnh được xử lý cục bộ trên ESP32-CAM và xóa ngay sau khi suy luận, không lưu trữ hoặc truyền ra ngoài trừ khi có yêu cầu rõ ràng phục vụ cải tiến mô hình. 

## **1.5.3 Khung tổ chức yêu cầu** 

Các yêu cầu được tổ chức theo chuỗi từ đề xuất giá trị → mục tiêu → kịch bản sử dụng (use cases) → yêu cầu chức năng → yêu cầu phi chức năng. 

_Hình 1. Cấu trúc của tài liệu_ 

## **1.6 Phạm vi và định vị sản phẩm** 

Dự án này vừa là một sản phẩm phần cứng vừa là một hệ thống AIoT có phần mềm đi kèm. Về mặt vật lý, thiết bị gồm từ một đến ba ngăn chứa - thông thường là ngăn rác hữu cơ, giấy và nhựa. Bộ điều khiển nhúng ESP32-CAM đọc dữ liệu cảm biến, điều khiển cơ cấu chấp hành, tiếp nhận kết quả phân loại từ mô hình AI và duy trì trạng thái an toàn của thiết bị. Thành phần AI phân tích hình ảnh từ camera và trả về nhãn loại rác tương ứng. Dashboard cục bộ hoặc trên đám mây (tuỳ chọn) lưu trữ dữ liệu telemetry và hiển thị trạng thái hệ thống cho người vận hành. 

Từ góc nhìn của người dùng (học sinh), sản phẩm cần có trải nghiệm đơn giản: người dùng đưa vật phẩm rác đến trước camera, chờ hệ thống nhận diện trong giây lát, sau đó bỏ rác vào đúng ngăn được chỉ định. Từ góc nhìn của người vận hành (nhà trường), sản phẩm cần cung cấp thông báo đáng tin cậy khi thùng đầy, thông tin trạng thái bảo trì và dữ liệu thống kê chứng minh rác đang được phân loại đúng cách. 

Trang 11 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

_Hình 2. Tổng quan hệ thống “Thùng rác thông minh”_ 

_**Bảng 3: Phạm vi và Giới hạn sản phẩm**_ 

|**Trong phạm vi**|**Ngoài phạm vi**|
|---|---|
|Phân loại rác bằng AI thành ba loại: hữu cơ,<br>giấy và nhựa.|Xử lý chất thải nguy hại công nghiệp hoặc<br>phân tích hóa học|
|Điều khiển servo mở nắp đúng ngăn theo kết<br>quả phân loại|Lập lịch tự động cho xe thu gom rác|
|Phát hiện thùng đầy và gửi thông báo lên hệ<br>thống|Hệ thống thanh toán và hóa đơn quản lý rác<br>đô thị|
|Lưu trữ telemetry và dashboard/API cơ bản|Nền tảng trao đổi phế liệu công khai|
|Thiết kế vỏ hộp nguyên mẫu và kiến trúc phần<br>cứng|Chứng nhận sản xuất hàng loạt|



## **1.7 Các lớp kỹ thuật** 

_**Bảng 4: Các lớp kỹ thuật và chi phí tham khảo[3]**_ 

|**Lớp**|**Thành phần chính**|**Vai trò**|
|---|---|---|
|Lớp vật lý|Vật liệu vỏ thùng (Bìa carton 60cmx30cm)|Chứa và phân tách rác sau khi<br>phân loại|



_3 Xem chi tiết giá tham khảo cho từng thiết bị ở mục phụ lục A_ 

Trang 12 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Lớp**|**Thành phần chính**|**Vai trò**|
|---|---|---|
|Lớp<br>cảm<br>biến|Cảm biến siêu âm HC-SR04 (×4), cảm biến<br>hồng ngoại vật cản IR HC-SR501 (PIR),<br>Camera OV2640|Phát hiện rác tiếp cận, đo mức độ<br>đầy từng ngăn, chụp ảnh phân<br>loại|
|Lớp cơ cấu<br>chấp hành|Động cơ servo SG90 (×3), LED báo hiệu<br>(×3 màu)|Mở đúng nắp ngăn, hiển thị trạng<br>thái thùng đầy|
|Lớp nhúng|Kit phát triển Wi-Fi BLE ESP32 Camera<br>ESP32-CAM<br>Development<br>Board<br>Ai-Thinker|Đọc cảm biến, điều khiển servo,<br>nhận kết quả AI, quản lý trạng<br>thái thiết bị|
|Lớp AI|Camera module, mô hình phân loại ảnh<br>(TensorFlow Lite), chạy cục bộ trên<br>ESP32-CAM|Dự đoán loại rác và điểm tin cậy<br>từ ảnh đầu vào|
|Lớp<br>giao<br>tiếp|Wi-Fi tích hợp ESP32-CAM, giao thức<br>MQTT / HTTP, broker Mosquitto hoặc dịch<br>vụ đám mây (HiveMQ Free / Firebase)|Gửi telemetry, nhận cấu hình, đẩy<br>thông báo thùng đầy lên hệ thống|
|Lớp<br>ứng<br>dụng|Dashboard web (Node-RED / Grafana / web<br>app tự xây), dịch vụ thông báo (Firebase<br>FCM / email), API, cơ sở dữ liệu (SQLite /<br>PostgreSQL / Firebase Realtime DB)|Giám sát thùng rác, xem sự kiện<br>phân loại, thống kê rác tái chế<br>theo ngăn, hỗ trợ tích điểm<br>thưởng|



## **1.8 Các lớp người dùng, đặc điểm và quyền truy cập của người dùng** 

## **1.8.1 Quyền truy cập của người dùng cuối** 

Người dùng cuối chủ yếu là học sinh mầm non, tiểu học hoặc người sử dụng thùng rác trong khuôn viên trường học. Họ tương tác trực tiếp với hệ thống bằng cách đưa rác vào vùng chờ trước camera để hệ thống tự động nhận diện và mở đúng ngăn chứa phù hợp. 

Nhóm người dùng này không cần tài khoản đăng nhập hoặc kiến thức kỹ thuật. Toàn bộ quá trình sử dụng phải đơn giản, trực quan, có phản hồi rõ ràng thông qua đèn LED, âm thanh hoặc màn hình hiển thị nhằm hỗ trợ trẻ nhỏ sử dụng dễ dàng và hình thành thói quen phân loại rác đúng cách. 

## **1.8.2 Quyền truy cập của nhân viên vận hành** 

Nhân viên vận hành hoặc lao công chịu trách nhiệm đổ rác, vệ sinh thùng, kiểm tra cảm biến và xử lý các cảnh báo vận hành. 

Họ có thể truy cập dashboard hoặc ứng dụng thông báo để xem: 

- Trạng thái kết nối của từng thùng rác. 

- Mức độ đầy của từng ngăn chứa. 

Trang 13 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

- Các cảnh báo đầy rác hoặc lỗi thiết bị. 

- Lịch sử hoạt động và sự kiện gần đây. 

Mục tiêu của nhóm này là giảm việc kiểm tra thủ công và hỗ trợ bảo trì thiết bị đúng thời điểm. 

## **1.8.3 Quyền truy cập của quản trị viên hệ thống** 

Quản trị viên hệ thống chịu trách nhiệm cấu hình thiết bị và quản lý nền tảng backend của hệ thống. 

Các quyền truy cập bao gồm: 

- Quản lý cấu hình mạng và kết nối thiết bị. 

- Cấu hình ngưỡng cảnh báo đầy rác. 

- Quản lý dashboard, API và dữ liệu telemetry. 

- Theo dõi log lỗi và trạng thái hoạt động của hệ thống. 

- Quản lý tài khoản và phân quyền người vận hành. 

Tất cả các chức năng quản trị phải yêu cầu xác thực để đảm bảo an toàn hệ thống và bảo vệ dữ liệu vận hành. 

## **1.8.4 Truy cập AI và bảo trì** 

Nhóm AI và bảo trì kỹ thuật chịu trách nhiệm hiệu chỉnh hệ thống và duy trì độ chính xác của mô hình phân loại rác. 

Các quyền truy cập có thể bao gồm: 

- Cập nhật hoặc thay thế mô hình AI. 

- Điều chỉnh ngưỡng độ tin cậy của mô hình. 

- Hiệu chuẩn cảm biến siêu âm, servo và camera. 

- Kiểm tra các mẫu dữ liệu phân loại đã được ẩn danh. 

- Theo dõi phiên bản firmware và phiên bản model AI. 

Do các thay đổi trong nhóm quyền này có thể ảnh hưởng trực tiếp đến hành vi phân loại và độ ổn định của hệ thống, mọi thao tác bảo trì và cập nhật phải được kiểm soát và ghi log đầy đủ. 

## **1.9 Tài liệu Người dùng** 

Hệ thống cần cung cấp đầy đủ tài liệu hướng dẫn cho người dùng, nhân viên vận hành và nhóm phát triển nhằm hỗ trợ triển khai, sử dụng và bảo trì prototype. 

Các tài liệu bao gồm: 

- Tài liệu hướng dẫn khởi động nhanh cho việc lắp đặt và cấp nguồn thiết bị. 

- Hướng dẫn sử dụng dành cho học sinh và người dùng cuối khi bỏ rác và theo dõi phản hồi từ hệ thống. 

- Tài liệu bảo trì cho việc vệ sinh thùng rác, làm sạch khu vực camera và kiểm tra cảm biến. 

- Tài liệu hiệu chuẩn cảm biến siêu âm, servo và các thành phần phần cứng liên quan. 

Trang 14 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

- Tài liệu API và telemetry dành cho nhóm phát triển dashboard, backend hoặc hệ thống thông báo. 

- Tài liệu xử lý sự cố cơ bản đối với các lỗi thường gặp như mất kết nối mạng, lỗi cảm biến hoặc servo bị kẹt. 

## **1.10 Ràng buộc thiết kế và triển khai** 

## **1.10.1 Ràng buộc thiết kế** 

- Prototype phải hỗ trợ tối thiểu 1 ngăn để demo, mục tiêu hoàn chỉnh là 3 ngăn. 

- Vị trí camera phải nhìn thấy vật phẩm trước khi rác rơi vào thùng. 

- Cơ cấu nắp/máng phải tránh kẹt tay và tránh servo chịu tải quá lâu. 

- Vỏ thùng phải dễ mở để thay túi rác, vệ sinh cảm biến và chỉnh lại camera. 

- Tín hiệu LED phải dễ nhìn trong môi trường lớp học hoặc hành lang. 

## **1.10.2 Ràng buộc triển khai** 

- Thiết bị vẫn phải nhận rác và mở nắp cơ bản khi mất mạng. 

- Nguồn servo cần tách hoặc ổn áp đủ dòng để không reset bộ điều khiển. 

- AI model phải đủ nhẹ cho thiết bị xử lý được hoặc có luồng inference ngoài thiết bị rõ ràng. 

- Mọi telemetry phải có device_id, timestamp và trạng thái gửi/đồng bộ. 

- Hai tuần cuối không thêm tính năng lớn; chỉ test, sửa lỗi, nâng cấp giao diện/mô hình và chuẩn bị demo. 

## **1.11 Giả định và sự phù hợp với chính sách** 

## **1.11.1 Giả định** 

- Thiết bị được đặt trong nhà hoặc khu vực bán ngoài trời có mái che. 

- Mỗi lần sử dụng, người dùng đưa một vật phẩm hoặc một nhóm vật phẩm cùng loại. 

- Ba loại rác chính trong prototype là hữu cơ, giấy và nhựa. 

- Dataset AI được thu thập từ vật phẩm thường gặp ở trường học: chai, giấy, hộp, đồ ăn thừa, bao bì. 

- Kết nối mạng có thể không ổn định nên cần cơ chế lưu tạm dữ liệu. 

## **1.11.2 Sự phù hợp với chính sách nhà trường, quyền riêng tư và tính bền vững** 

Dự án phù hợp với mục tiêu giáo dục môi trường, giảm rác bỏ sai và thúc đẩy thói quen phân loại rác từ sớm. Vì thiết bị có camera ở khu vực công cộng, ảnh phải được xử lý theo nguyên tắc tối thiểu dữ liệu: chỉ lưu khi cần debug và phải tránh ghi nhận thông tin nhận dạng học sinh. 

## **1.11.3 Chính sách cần phát triển** 

- Chính sách lưu/xóa ảnh. 

- Chính sách bảo trì, vệ sinh và kiểm tra thiết bị. 

- Chính sách cập nhật model AI và kiểm thử lại trước khi dùng. 

Trang 15 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

- Chính sách phân quyền dashboard. 

- Quy trình xử lý sự cố: đầy thùng, mất mạng, kẹt servo, camera bị che hoặc phân loại sai lặp lại. 

Trang 16 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

## **2. Đề xuất giá trị, các kịch bản sử dụng và yêu cầu chức năng** 

## **2.1 Từ giá trị cốt lõi đến yêu cầu kỹ thuật hệ thống** 

Ý tưởng cốt lõi của Thùng rác thông minh là biến việc phân loại rác tại các trường mầm non và tiểu học trở nên hoàn toàn tự động, chính xác, giúp nhà trường dễ dàng quản lý và theo dõi. Thay vì ép các em nhỏ phải nhớ những quy tắc phân loại khô khan, hệ thống sử dụng camera và cảm biến để tự nhận diện rác và mở nắp, tạo ra một trải nghiệm học tập tương tác thú vị. Phần đặc tả dưới đây sẽ chuyển đổi những giá trị thực tế này thành các tính năng kỹ thuật chi tiết: 

_**Bảng 5: Ánh xạ từ Giá trị cốt lõi đến Yêu cầu kỹ thuật**_ 

|**Giá trị cốt lõi**|**Năng lực của hệ**<br>**thống**|**Yêu cầu kỹ thuật**|
|---|---|---|
|Giúp học sinh nhỏ<br>tuổi bỏ rác đúng<br>nơi quy định|Phân loại rác bằng<br>Trí tuệ nhân tạo AI|Mô hình xử lý ảnh qua camera phải nhận diện<br>chính xác rác theo các loại bao gồm rác thải hữu<br>cơ, nhựa và giấy để đưa ra quyết định phân loại.|
|Giúp các em bỏ rác<br>dễ dàng không cần<br>chạm tay vào thùng|Tự động điều khiển<br>đóng mở nắp bằng<br>động cơ Servo|Sau khi đã phân loại xong, hệ thống cần tự động<br>mở đúng thùng rác tương ứng để học sinh có thể<br>bỏ rác vào.|
|Giữ vệ sinh trường<br>học và tránh rác bị<br>tràn ra ngoài|Giám sát dung tích<br>thực tế và phát<br>cảnh báo đầy rác|Hệ thống phải dùng cảm biến siêu âm để đo mức<br>rác liên tục bên trong và tự động gửi thông báo về<br>máy chủ quản lý khi rác chạm ngưỡng đầy.|
|Tạo động lực thi<br>đua phân loại rác<br>cho học sinh|Kết<br>nối<br>mạng<br>Internet và cập nhật<br>bảng thống kê|Hệ thống phải lưu lại số lần bỏ rác và số lần bỏ rác<br>tái chế đồng thời đồng bộ dữ liệu theo thời gian<br>thực lên trang web quản lý để nhà trường dùng làm<br>cơ sở tích điểm thưởng.|



## **2.2 Mục đích và ranh giới hệ thống** 

## **2.2.1 Mục đích** 

Mục đích mà hệ thống phải đạt được là **“Xây dựng hệ thống thùng rác thông minh hỗ trợ học sinh phân loại rác (nhựa, giấy, hữu cơ) và giúp nhà trường giám sát quá trình phân loại rác tự động”** . 

Để đạt được mục đích này, dự án phải duy trì trong dài hạn ba mục tiêu: nhận diện và phân loại rác thông minh, giám sát và điều khiển động cơ thông minh, thông báo và thống kê rác. Mỗi mục tiêu cùng hỗ trợ việc tự động hóa quy trình phân loại rác, giảm sai sót khi học sinh bỏ rác và giúp nhà trường theo dõi hoạt động của hệ thống một cách trực quan. 

Trang 17 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

_Hình 3. Mục đích và các mục tiêu của hệ thống thùng rác thông minh AIoT_ **[4]** 

**Lý do thực tiễn:** Việc giúp các em học sinh nhỏ tuổi phân loại rác chính xác ngay tại lớp học sẽ nâng cao chất lượng thu gom các nhóm rác tái chế. Giúp không gian lớp học sạch sẽ hơn, không bị bốc mùi do rác để lẫn lộn, từ đó nâng cao chất lượng môi trường giáo dục của nhà trường. 

**Động lực phát triển:** Đồ án xuất phát từ mong muốn nâng cao ý thức bảo vệ môi trường cho thế hệ trẻ là mầm non của đất nước, giữ gìn vệ sinh không gian học đường. 

**Sản phẩm mong đợi:** Mô hình thùng rác thông minh thực tế phải thực hiện được mọi tính năng bao gồm đưa rác trước camera để máy tự nhận diện, nắp thùng tự động bật mở cho bé bỏ rác vào, đèn báo hiệu chuyển sang màu đỏ khi bên trong đã đầy rác và gửi ngay tin nhắn thông báo cho người quản lý trường học. 

## **2.2.2 Ranh giới hệ thống** 

> 4Trong các sơ đồ, [Goal] đại diện cho mục đích chính của hệ thống 

Trang 18 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

_Hình 4. Tổng quan các use case được xác định trong giai đoạn đầu thiết kế hệ thống_ _**Bảng 6: Ranh giới hệ thống Thùng rác thông minh**_ 

|**Thành phần bên trong**|**Tác nhân bên ngoài**|**Phương thức kết nối giao tiếp**|
|---|---|---|
|Thiết bị camera quét ảnh<br>và mô hình trí tuệ nhân<br>tạo AI|Học sinh mầm non và tiểu<br>học|Camera thu nhận luồng hình ảnh<br>trực tiếp từ hành động đưa rác của<br>học sinh vào vùng chờ để mô hình<br>AI phân tích và ra quyết định.|
|Mạch điều khiển trung<br>tâm và động cơ Servo<br>điều khiển nắp|Học sinh mầm non và tiểu<br>học|Động cơ Servo nhận lệnh từ hệ<br>thống để tự động mở hoặc đóng nắp<br>các ngăn chứa tương ứng cho học<br>sinh bỏ rác vào.|



Trang 19 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

Cảm biến siêu âm đo Học sinh và nhân viên lao khoảng cách và đèn công LED tín hiệu Module truyền thông Nhân viên quản lý Wi-Fi và bộ nhớ lưu trữ dữ liệu 

Cảm biến siêu âm đo lượng rác bên trong để điều khiển đèn LED đổi màu chuyển sang màu xanh hoặc màu đỏ hiển thị trực quan cho người dùng. 

Module Wi-Fi gửi dữ liệu lưu trữ về lịch sử bỏ rác và cảnh báo thùng đầy lên hệ thống máy chủ qua mạng Internet để hiển thị trên trang web quản lý. 

_**Bảng 7: Các trường hợp sử dụng theo mục tiêu và tác nhân**_ 

|**Mục tiêu**||**Use Cases**|**ID**|**Specialised Use Cases**|**Tác nhân**|
|---|---|---|---|---|---|
|1. Hệ thống tự động<br>phân loại rác thành 3<br>nhóm (hữu cơ, giấy,<br>nhựa) với độ chính xác<br>≥ 85% và thời gian<br>phản hồi ≤ 5 giây<br>trong điều kiện ánh<br>sáng trong nhà||Đưa rác vào<br>vùng chờ|UC1|Học sinh đưa rác vào vùng<br>chờ; camera chụp ảnh vật<br>phẩm; hệ thống báo chờ<br>khi đangxử lý.|Học sinh mầm<br>non và tiểu<br>học|
|||Phân loại rác<br>bằng Trí tuệ<br>nhân tạo AI|UC2|Tiền xử lý ảnh; dự đoán<br>nhóm rác và điểm tin cậy;<br>từ chối kết quả khi độ tin<br>cậy thấp.|Hệ Thống<br>(Mô hình phân<br>loại ảnh AI;<br>mạch điều<br>khiển trung<br>tâm)|
|2. Hệ thống tự động<br>mở đúng ngăn tương<br>ứng trong ≤ 5 giây sau<br>khi nhận kết quả phân<br>loại, sau khi đóng nắp<br>ghi nhận tín hiệu cảm<br>biến siêu âm và cập<br>nhật trạng thái đèn<br>trong ≤ 0.5 giây||Điều khiển<br>mở nắp ngăn<br>chứa rác phù<br>hợp|UC3|Tiếp nhận mã phân loại;<br>đối chiếu với ngăn chứa;<br>điều khiển servo mở/đóng<br>nắpan toàn.|Hệ thống<br>(Mạch điều<br>khiển; động<br>cơ Servo)|
|||Giám sát<br>lượng rác và<br>cập nhật đèn<br>tín hiệu|UC4|Cảm biến siêu âm đo mức<br>đầy; cập nhật trạng thái<br>dung lượng; LED đỏ nhấp<br>nháy khi đầy hoặc lỗi.|Hệ thống<br>(Cảm biến<br>siêu âm; hệ<br>thống đèn<br>LED)|



Trang 20 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Mục tiêu**||**Use Cases**|**ID**|**Specialised Use Cases**|**Tác nhân**|
|---|---|---|---|---|---|
|3. Dashboard nhận dữ<br>liệu từ mạch chính qua<br>Internet để cập nhật<br>trạng thái thùng vừa<br>ghi nhận rác trong ≤ 5<br>giây, hiển thị cảnh báo<br>khi vượt ngưỡng đầy<br>và lưu thống kê phân<br>loại theo ngày tối thiểu<br>30 ngày.||Ghi nhận<br>trạng thái<br>lượng rác|UC5|Firmware tính phần trăm<br>đầy; gửi cảnh báo lên<br>server; Dashboard/App<br>hiển thịngăn cần xử lý.|Nhân viên dọn<br>dẹp|
|||Thống kê<br>phân loại rác|UC6|Ghi nhận sự kiện phân<br>loại; gửi loại rác, mã thùng<br>và thời gian lên server;<br>tổng hợp theo loại, thùng<br>và ngày.|Quản lý|
|||Xem<br>dashboard<br>trạng thái<br>thùng|UC7|Hiển thị trạng thái kết nối;<br>hiển thị mức đầy từng<br>ngăn và thống kê rác; lọc<br>theo thùng, loại rác và thời<br>gian.|Quản lý; Nhân<br>viên dọn dẹp|
|||Cấu hình và<br>quản lý thiết<br>bị từ xa|UC8|Quản lý cập nhật ngưỡng<br>đầy cho từng ngăn; tải lên<br>model AI mới để cập nhật<br>xuống firmware; bật hoặc<br>tắt chế độ bảo trị. Lệnh<br>được lưu chờ nếu thiết bị<br>ngoại tuyến và thực thi tự<br>độngkhi có kết nối lại.|Quản lý|



**2.3 MỤC TIÊU 1: Hệ thống tự động phân loại rác thành 3 nhóm (hữu cơ, giấy, nhựa) với độ chính xác ≥ 85% và thời gian phản hồi ≤ 5 giây trong điều kiện ánh sáng trong nhà** 

**Mô tả:** Hệ thống tự động nhận diện và phân loại chính xác các nhóm rác gồm giấy, hữu cơ, nhựa tái chế tại vùng chờ với độ chính xác từ 85% trở lên. Kết quả phân tích hình ảnh này phải được xử lý nhanh chóng với thời gian phản hồi dưới 5 giây để đảm bảo trải nghiệm liền mạch cho học sinh trong giai đoạn thử nghiệm. 

**Lý do thực tế:** Khả năng nhận diện bằng trí tuệ nhân tạo chính là yếu tố cốt lõi biến chiếc thùng rác trở nên thông minh hoàn toàn, thay vì chỉ là một thiết bị đóng mở bằng cảm biến thông thường. 

**Động lực phát triển:** Độ chính xác khi phân loại, thời gian phản hồi nhanh chóng phù hợp với tính cách hiếu động của trẻ nhỏ và có phương án xử lý an toàn khi mô hình không chắc chắn về kết quả. 

Trang 21 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

_Hình 5. Mục tiêu 1_ 

## **2.3.1 Use Case: Đưa rác vào vùng chờ** 

_Hình 6 : Flowchart mô tả luồng Đưa rác vào vùng chờ_ 

_**Bảng 8: Use Case: Đưa rác vào vùng chờ**_ 

**Nội dung mô tả** 

**Mục** 

Trang 22 

|Tác nhân chính|Học sinh mầm non và tiểu học|
|---|---|
|Tác nhân kích hoạt|Có một vật thể xuất hiện gần vị trí cửa bỏ rác của thùng.|
|Điều kiện tiên quyết|Thùng rác đã được cắm điện và còn ít nhất một ngăn chứa bên trong<br>chưa bị đầy.|
|Luồng<br>hoạt<br>động<br>chính|1. Cảm biến vật lý phát hiện có vật thể rác thải đang tiếp cận vùng<br>chờ.<br>2. Thiết bị camera tiến hành chụp lại hình ảnh thực tế của rác thải.<br>3. Hệ thống bật đèn tín hiệu màu đỏ báo hiệu yêu cầu học sinh chờ<br>trong giây lát.|
|Điều kiện sau khi kết<br>thúc|Một bức ảnh chụp rõ nét về rác để đưa đi phân loại.|



## **2.3.2 Use Case: Phân loại rác bằng Trí tuệ nhân tạo AI** 

_Hình  7: Flowchart mô tả luồng Phân loại rác bằng Trí tuệ nhân tạo AI_ _**Bảng 9: Use Case: Phân loại rác bằng Trí tuệ nhân tạo AI**_ 

Trang 23 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Mục**|**Nội dung mô tả**|
|---|---|
|Tác nhân chính|Hệ Thống|
|Tác nhân kích hoạt|Hệ thống thu nhận được một bức ảnh rác thải hợp lệ từ camera.|
|Điều kiện tiên quyết|Mô hình AI đã được tải thành công lên bộ nhớ và bức ảnh chụp từ<br>camera.|
|Luồng<br>hoạt<br>động<br>chính|1. Hệ thống tiến hành cắt chỉnh kích thước và tiền xử lý bức ảnh vừa<br>chụp.<br>2. Mô hình AI phân tích các đặc trưng để dự đoán nhóm rác cùng với<br>độ tin cậy tương ứng.<br>3. Bộ lọc quyết định tiến hành so sánh độ tin cậy của dự đoán với<br>ngưỡng quy định ban đầu.<br>4. Hệ thống xuất ra mã kết quả phân loại cuối cùng của rác.|
|Luồng hoạt động thay<br>thế|Nếu mức độ tin cậy của AI thấp hơn ngưỡng quy định:<br>1. Hệ thống tự động bỏ qua kết quả phân loại không chắc chắn do vật<br>thể quá lạ.<br>2. Hệ thống tự động từ chối rác thải bằng cách không mở nắp thùng<br>và nhấp nháy đèn đỏ để thông báo.|
|Điều kiện sau khi kết<br>thúc|Hệ thống xác định được chính xác loại rác và sẵn sàng truyền tín<br>hiệu kích hoạt để mở nắp thùng.|



## **2.3.3 Các yêu cầu chức năng kỹ thuật** 

_**Bảng 10: Yêu cầu chức năng kỹ thuật cho** mục tiêu_ _**1**_ 

|**ID #**|**Nội dung mô tả**|**Mức độ**<br>**ưu tiên**|**Phân vùng**<br>**kỹ thuật**|**Nguồn gốc**|
|---|---|---|---|---|
|FREQ.<br>1|Phát hiện sự xuất hiện của rác thải khi học<br>sinh đưa vào vị trí bỏ rác.|Bắt buộc|Cảm biến|UC 2.3.1|
|FREQ.<br>2|Chụp lại hình ảnh thực tế của rác ngay khi<br>có tín hiệu kích hoạt từ cảm biến ở vùng<br>chờ.|Bắt buộc|Camera|UC 2.3.1|
|FREQ.<br>3|Phân loại rác thải thành các nhóm bao gồm<br>hữu cơ, giấy, nhựa|Bắt buộc|AI|UC 2.3.2|



Trang 24 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT|Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT||||
|---|---|---|---|---|
|FREQ.<br>4|Trả về một điểm số thể hiện mức độ tin cậy<br>hay độ chính xác tương ứng với mỗi kết quả<br>phân loại của AI.|Bắt buộc|AI|UC 2.3.2|
|FREQ.<br>5|Không mở nắp thùng rác nếu mức độ tin<br>cậy của mô hình AI nằm dưới ngưỡng quy<br>định đồng thời nhấp nháy đèn đỏ báo hiệu.|Bắt buộc|AI|UC 2.3.2|



## **2.4 MỤC TIÊU 2: Hệ thống tự động mở đúng ngăn tương ứng trong ≤ 5 giây sau khi nhận kết quả phân loại, sau khi đóng nắp ghi nhận tín hiệu cảm biến siêu âm và cập nhật trạng thái đèn trong ≤ 0.5 giây** 

**Mô tả:** Hệ thống tự động kích hoạt động cơ để đóng hoặc mở chính xác nắp thùng rác theo kết quả phân loại với độ trễ phản hồi dưới 5 giây. Sau khi nắp thùng đóng lại, dữ liệu về trạng thái đầy của từng ngăn chứa phải được ghi nhận thông qua tín hiệu cảm biến siêu âm và cập nhật trạng thái đèn trong ≤ 0.5 giây. 

**Lý do thực tế:** Việc tự động đóng mở nắp tương ứng với loại rác mà các em cần bỏ vào thùng và báo đầy rác giúp các em nhỏ bỏ rác sạch sẽ không cần chạm tay. Việc này không những giúp giữ gìn vệ sinh học đường mà còn giáo dục trẻ em về cách phân loại rác và ý thức bảo vệ môi trường từ sớm. 

**Động lực phát triển:** Cơ chế đóng mở nắp nhanh chóng, an toàn tuyệt đối cho trẻ nhỏ khi tiếp xúc. 

Trang 25 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

_Hình 6. Mục tiêu 2_ 

## **2.4.1 Use Case: Điều khiển mở nắp ngăn chứa rác phù hợp** 

_Hình 8: Flowchart mô tả luồng điều khiển mở nắp ngăn chứa rác phù hợp_ 

_**Bảng 11: Use Case: Điều khiển mở nắp ngăn chứa rác phù hợp**_ 

|**Mục**|**Nội dung mô tả**|
|---|---|
|Tác nhân chính|Hệ Thống|
|Tác nhân kích hoạt|Mạch điều khiển nhận được tín hiệu kết quả phân loại rác từ mô<br>hình AI.|



Trang 26 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|Điều kiện tiên quyết|Thùng rác được cung cấp điện để hoạt động bình thường và ngăn<br>chứa rác mục tiêu vẫn còn chỗ trống.|
|---|---|
|Luồng<br>hoạt<br>động<br>chính|1. Mạch điều khiển tiếp nhận mã kết quả của nhóm rác vừa được<br>phân loại xong.<br>2. Hệ thống đối chiếu mã kết quả này với vị trí các ngăn chứa rác<br>thực tế trong thùng.<br>3. Mạch điều khiển truyền lệnh điều khiển dòng điện đến động cơ<br>Servo của ngăn rác được chọn.<br>4. Động cơ Servo quay để tự động mở nắp ngăn chứa phù hợp cho<br>học sinh bỏ rác.<br>5. Động cơ Servo tự động quay trở lại vị trí đóng nắp ban đầu để<br>đảm bảo vệ sinh.|
|Luồng hoạt động thay<br>thế|Ngăn chứa rác mục tiêu đã bị đầy:<br>1. Mạch điều khiển phát hiện ngăn rác định mở đang ở trạng thái đầy<br>dựa trên dữ liệu từ cảm biến siêu âm.<br>2. Hệ thống hủy lệnh mở nắp ngăn đó để tránh tình trạng rác bị tràn<br>ra ngoài.<br>3. Đèn LED màu đỏ nhấp nháy để báo hiệu đầy rác.|
|Điều kiện sau khi kết<br>thúc|Động cơ hoàn thành việc đóng mở nắp an toàn và rác đã nằm gọn<br>bên trong thùng.|



Trang 27 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

## **2.4.2 Use Case: Giám sát lượng rác và cập nhật đèn tín hiệu** 

_Hình 9: Flowchart mô tả luồng điều khiển mở nắp ngăn chứa rác phù hợp_ _**Bảng 12: Use Case: Giám sát lượng rác và cập nhật đèn tín hiệu**_ 

|**Mục**|**Nội dung mô tả**|
|---|---|
|Tác nhân chính|Hệ Thống.|
|Tác nhân kích hoạt|Hệ thống cảm biến siêu âm tiến hành đo khoảng cách sau khi nắp<br>thùng đóng lại.|
|Điều kiện tiên quyết|Thùng rác đã được cấp nguồn điện và các mắt cảm biến không bị che<br>khuất bởi vật cản cố định.|



Trang 28 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|Luồng<br>hoạt<br>động<br>chính|1. Cảm biến siêu âm phát sóng và đo khoảng cách phản hồi từ nắp<br>thùng rác đến bề mặt rác.<br>2. Hệ thống so sánh khoảng cách thực tế với ngưỡng cảnh báo đầy<br>quy định ban đầu.<br>3. Từ kết quả so sánh, hệ thống cập nhật từng trạng thái dung lượng<br>rác cho mỗi thùng.<br>4. Hệ thống điều khiển chuyển đèn LED sang màu đỏ nhấp nháy liên<br>tục nếu lượng rác vượt quá ngưỡng cảnh báo đầy.|
|---|---|
|Luồng hoạt động thay<br>thế|Cảm biến siêu âm gặp lỗi hoặc trả về giá trị sai lệch:<br>1. Mạch điều khiển phát hiện tín hiệu từ cảm biến siêu âm bị mất kết<br>nối hoặc trả về giá trị âm hoặc giá trị sai lệch trong một thời gian dài.<br>2. Hệ thống tự động kích hoạt chế độ cảnh báo an toàn, đèn LED màu<br>đỏ chuyển sang nhấp nháy liên tục màu đỏ và thông báo cho nhân<br>viên đến kiểm tra trực tiếp.|
|Điều kiện sau khi kết<br>thúc|Trạng thái lượng rác của các ngăn chứa luôn được cập nhật liên tục<br>và hiển thị trực quan thông qua màu sắc đèn LED.|



## **2.4.3 Các yêu cầu chức năng kỹ thuật** 

_**Bảng 13: Yêu cầu chức năng kỹ thuật cho mục tiêu 2**_ 

|**ID #**|**Nội dung mô tả**|**Mức độ**<br>**ưu tiên**|**Phân**<br>**vùng**<br>**kỹ thuật**|**Nguồn gốc**|
|---|---|---|---|---|
|FREQ.1|Tiếp nhận kết quả phân loại nhóm rác từ<br>mô hình AI để xác định thùng đựng rác<br>tương ứng.|Bắt buộc|Phần<br>mềm<br>nhúng|UC 2.4.1|
|FREQ.2|Điều khiển động cơ Servo quay để mở<br>nắp thùng đựng rác tương ứng.|Bắt buộc|Thiết<br>bị<br>ngoại vi|UC 2.4.1|
|FREQ.3|Tự động điều khiển đóng nắp thùng rác<br>sau tối đa 5 giây chờ.|Bắt buộc|Phần<br>mềm<br>nhúng|UC 2.4.1|
|FREQ.4|Thông báo không xác định được loại rác<br>thông qua đèn LED đỏ nhấp nháy.|Bắt buộc|Thiết<br>bị<br>ngoại vi|UC 2.4.1|
|FREQ.5|Phát hiện trạng thái đầy rác của từng ngăn<br>chứa bằng việc đo khoảng cách của cảm<br>biến siêu âm.|Bắt buộc|Cảm biến|UC 2.4.2|



Trang 29 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

FREQ.6 Điều khiển đèn LED màu đỏ nhấp nháy Bắt buộc Thiết bị UC 2.4.2 trên nắp thùng để báo hiệu đầy rác. ngoại vi 

**2.5 MỤC TIÊU 3: Dashboard nhận dữ liệu từ mạch chính qua Internet để cập nhật trạng thái thùng vừa ghi nhận rác trong ≤ 5 giây, hiển thị cảnh báo khi vượt ngưỡng đầy và lưu thống kê phân loại theo ngày tối thiểu 30 ngày** 

**Mô tả:** Dashboard sẽ nhận dữ liệu từ mạch chính qua Internet để cập nhật và hiển thị trạng thái thùng vừa được ghi nhận rác trên mạch trong ≤ 5 giây, hiển thị cảnh báo khi vượt ngưỡng đầy 0.8 và hiển thị thống kê phân loại theo từng loại rác, từng ngăn và theo ngày với dữ liệu lưu trữ tối thiểu 30 ngày. Ngoài ra, quản trị viên có thể cấu hình ngưỡng đầy, cập nhật model AI, bật chế độ bảo trì thiết bị từ xa thông qua dashboard. 

**Lý do thực tế:** Cập nhật trạng thái thùng và thống kê phân loại theo ngày giúp nhà trường và nhân viên vệ sinh chủ động thu gom rác kịp thời, giữ gìn cảnh quan sạch đẹp; đồng thời cung cấp số liệu trực quan để đánh giá, cho điểm thi đua, giáo dục và nâng cao ý thức phân loại rác của các em học sinh. Khả năng cấu hình từ xa giúp vận hành và bảo trì hệ thống mà không cần tiếp cận trực tiếp thiết bị. 

**Động lực phát triển:** Ngăn ngừa tràn rác khỏi thùng, dọn dẹp đúng lúc, giảm thiểu kiểm tra thủ công và cung cấp dữ liệu vận hành cho nhân viên và quản lý. Cấu hình từ xa giúp nhóm kỹ thuật hoặc quản lý cập nhật model AI và điều chỉnh thông số mà không cần can thiệp vật lý vào thiết bị sau khi triển khai. 

_Hình 7. Mục tiêu 3_ 

Trang 30 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

## **2.5.1 Use Case: Ghi nhận trạng thái lượng rác** 

_Hình 10: Flowchart mô tả luồng ghi nhận trạng thái lượng rác_ 

_**Bảng 14: Use Case: Ghi nhận trạng thái lượng rác**_ 

|**Mục**|**Mô tả**|
|---|---|
|Tác nhân chính|Nhân viên dọn dẹp.|
|Sự kiện kích hoạt|Mỗi khi mạch chính ghi nhận một lần bỏ rác thành công.|
|Điều kiện trước|Thùng rác hoạt động bình thường, có kết nối mạng và lưu trữ cục bộ.|



Trang 31 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Mục**|**Mô tả**|
|---|---|
|Luồng chính|1. Cảm biến đọc khoảng cách liên tục.<br>2. Firmware tính phần trăm đã đầy.<br>3. Gửi dữ liệu của cảm biến siêu âm lên server (cảnh báo nếu đã đầy).<br>4. Dashboard/App hiển thị dữ liệu (cảnh báo rác đầy) kèm ngăn cụ thể<br>cho nhân viên dọn dẹp và quản lý.|
|Luồng thay thế|1. Mất kết nối mạng.<br>2. Lưu dữ liệu tạm thời trên thiết bị.<br>3. Tự động gửi lại khi có mạng.|
|Điều kiện sau|Nhân viên biết đúng thùng nào cần đổ.|



## **2.5.2 Use Case: Thống kê phân loại rác** 

_Hình 11: Flowchart mô tả luồng thống kê phân loại rác_ 

Trang 32 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

_**Bảng 15: Use Case: Thống kê phân loại rác**_ 

|**Mục**|**Mô tả**|
|---|---|
|Tác nhân chính|Quản lý, Nhân viên dọn dẹp|
|Sự kiện kích hoạt|Mỗi lần AI phân loại rác thành công và rác được bỏ vào đúng ngăn|
|Luồng chính|1. ESP32-CAM ghi nhận kết quả phân loại<br>2. Gửi sự kiện lên server (loại rác, thùng, thời gian)<br>3. Server sẽ cộng dồn thống kê<br>4. Dashboard hiển thị phần trăm lượng theo từng loại rác, theo từng<br>thùng, theo ngày|
|Luồng thay thế|1. Mất kết nối<br>2. Lưu sự kiện cục bộ<br>3. Đồng bộ khi đã có mạng|
|Điều kiện sau|Quản lý xem được thống kê lượng các loại rác tái chế theo thời gian|



## **2.5.3 Use Case: Xem dashboard trạng thái thùng** 

_Hình 12: Flowchart mô tả luồng xem dashboard trạng thái thùng_ 

_**Bảng 16: Use Case: Xem dashboard trạng thái thùng**_ 

Trang 33 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Mục**|**Mô tả**|
|---|---|
|Tác nhân chính|Quản lý, Nhân viên dọn dẹp.|
|Sự kiện kích hoạt|Người dùng mở dashboard hoặc nhận được cảnh báo.|
|Luồng chính|1. Dashboard liệt kê danh sách thùng và trạng thái kết nối.<br>2. Hiển thị mức đầy từng ngăn, thống kê rác theo loại, thời gian cập<br>nhật, điểm cộng từ số lần vứt rác,..|
|Luồng thay thế|1. Thiết bị ngoại tuyến.<br>2. Dashboard hiển thị trạng thái mất kết nối kèm dữ liệu từ lần gửi<br>trạng thái cuối cùng.|
|Điều kiện sau|Người dùng nắm được trạng thái hiện tại của toàn bộ hệ thống thùng rác.|



## **2.5.4 Use Case: Cấu hình và quản lý thiết bị từ xa** 

_Hình 13: Flowchart mô tả luồng cấu hình và quản lý thiết bị từ xa_ _**Bảng 17: Use Case: Cấu hình và quản lý thiết bị từ xa**_ 

Trang 34 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Mục**|**Mô tả**|
|---|---|
|Tác nhân chính|Quản lý|
|Sự kiện kích hoạt|Quản trị viên mở trang cấu hình hoặc quản lý thiết bị trên dashboard|
|Luồng chính|1. Quản trị viên chọn thiết bị cần cấu hình.<br>2. Quản trị viên: cập nhật ngưỡng đầy cho từng ngăn, tải lên file<br>model AI mới  hoặc bật chế độ bảo trì thiết bị.<br>3. Server lưu lệnh và đẩy xuống firmware.<br>4. Firmware nhận lệnh, xác nhận và áp dụng ngay.<br>5. Dashboard hiển thị trạng thái thực thi lệnh thành công.|
|Luồng thay thế|1. Thiết bị đang ngoại tuyến: Server lưu lệnh chờ.<br>2. Khi firmware kết nối lại, lệnh được gửi xuống và áp dụng tự động.<br>3. Dashboard hiển thị trạng thái "chờ đồng bộ"|
|Điều kiện sau|Thiết bị hoạt động theo cấu hình mới hoặc trạng thái mới đã được quản trị<br>viên thiết lập|



## **2.5.5 Các yêu cầu chức năng kỹ thuật** 

_**Bảng 18: Yêu Cầu Chức Năng cho mục tiêu 3**_ 

|**ID #**|**Mô tả**|**Ưu tiên**|**Miền**|**Nguồn**|
|---|---|---|---|---|
|FREQ.1|Tạo thông báo đầy gồm chứa mã thiết bị, tên<br>ngăn, phần trăm đầy và thời gian khi mức đầy<br>đạt hoặc vượt ngưỡng đã cấu hình. Hiển thị<br>lên dashboard.|Bắt buộc|Thông báo|UC 2.5.1|
|FREQ.2|Lưu lại thông tin, thông báo trạng thái thùng<br>cục bộ khi mất mạng và đồng bộ khi có mạng<br>lại.|Nên có|Firmware|UC 2.5.1|
|FREQ.3|Ghi nhận mỗi sự kiện phân loại thành công lên<br>server.|Bắt buộc|Dữ liệu|UC 2.5.2|
|FREQ.4|Sự kiện phân loại phải chứa loại rác, mã thùng<br>và thời gian.|Bắt buộc|Dữ liệu|UC 2.5.2|
|FREQ.5|Tổng hợp thống kê theo loại rác, loại thùng,<br>theo ngày và theo tháng.|Bắt buộc|Thống kê|UC 2.5.2|
|FREQ.6|Hiển thị mức đầy, trạng thái kết nối và thống<br>kê rác trên dashboard.|Bắt buộc|Dashboard|UC 2.5.3|



Trang 35 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**ID #**|**Mô tả**|**Ưu tiên**|**Miền**|**Nguồn**|
|---|---|---|---|---|
|FREQ.7|Hiển thị trạng thái ngoại tuyến với dữ liệu cập<br>nhật lần cuối.|Nên có|Dashboard|UC 2.5.3|
|FREQ.8|Cho phép lọc thống kê theo thùng, loại rác và<br>khoảng thời gian.|Nên có|Dashboard|UC 2.5.3|
|FREQ.9|Cho phép cấu hình ngưỡng đầy riêng cho từng<br>ngăn trên dashboard và cập nhật về mạch<br>(ngưỡng mặc định 0.8).|Bắt buộc|Cấu hình|UC 2.5.4|
|FREQ.10|Cho phép quản trị viên tải lên file model AI<br>mới từ dashboard; server lưu và đẩy xuống<br>firmware khi thiết bị online, firmware xác<br>nhận phiên bản sau khi áp dụng thành công.|Nên có|Firmware|UC 2.5.4|
|FREQ.11|Cho phép quản trị viên bật hoặc tắt chế độ bảo<br>trì từ dashboard; firmware tạm dừng nhận rác<br>và hiển thị đèn báo bảo trì cho đến khi nhận<br>lệnh tiếp theo.|Nên có|Firmware|UC 2.5.4|



## **3. Yêu cầu phi chức năng** 

## **3.1 Yêu cầu chất lượng khi vận hành** 

## **3.1.1 Hiệu năng** 

**Căn cứ** : Học sinh tiểu học và mẫu giáo có thói quen hiếu động, không kiên nhẫn chờ đợi lâu, do đó toàn bộ chu kỳ từ đưa rác vào vùng chờ đến khi nắp mở phải đủ nhanh để không gây gián đoạn. 

**Động lực** : Nếu hệ thống phản hồi chậm (> 5 giây), học sinh có thể bỏ rác bừa hoặc mất hứng thú sử dụng, làm giảm giá trị giáo dục của sản phẩm. 

**Ánh xạ tới yêu cầu** : NFREQ.1, NFREQ.2, NFREQ.3, NFREQ.4, NFREQ.5, NFREQ.19 

_**Bảng 19: Chiến lược Hiệu năng**_ 

|**Hành động**|**Chiến lược**|
|---|---|
|Tối ưu thời gian inference AI. Đảm bảo<br>servo phản hồi nhanh. Tự động đóng nắp<br>theo timer cố định. Gửi thông báo đầy<br>thùng không đồng bộ (async).|Dùng model nhẹ CNN nhẹ (tự train)<br>Đặt timeout PWM servo. Dùng thread riêng cho<br>timer đóng nắp. Tách luồng gửi gửi thông báo<br>trạng thái đầy khỏi luồng điều khiển chính.|



## **3.1.2 Lưu trữ dữ liệu** 

Trang 36 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

**Căn cứ** : Theo dõi rác thải từng ngày trong 1 tháng gần nhất và trong tương lai hỗ trợ Dashboard và hệ thống tích điểm thưởng cần dữ liệu lịch sử đủ dài để nhà trường theo dõi xu hướng phân loại rác theo tuần và tháng. 

**Động lực** : Thiếu dữ liệu lịch sử làm giảm giá trị phân tích và không hỗ trợ được các báo cáo định kỳ cho ban giám hiệu. 

**Ánh xạ tới yêu cầu** : NFREQ.6. 

_**Bảng 20: Chiến lược Lưu trữ dữ liệu**_ 

|**Hành động**|**Chiến lược**|
|---|---|
|Lưu mọi sự kiện phân loại kèm timestamp lên<br>server. Giữ bản ghi tối thiểu 30 ngày. Xóa dữ<br>liệu cũ hơn.|Dùng cơ sở dữ liệu có cơ chế tự dọn dẹp<br>(TTL hoặc cron job). Lưu cục bộ khi mất<br>mạng, đồng bộ khi có kết nối lại.|



## **3.1.3 Khả năng mở rộng** 

**Căn cứ:** Hệ thống có thể bắt đầu với 1 thùng prototype nhưng cần hỗ trợ nhiều thùng ở nhiều vị trí khác nhau mà không cần thiết kế lại kiến trúc. 

**Động lực:** Triển khai thực tế tại các trường học có thể cần nhiều thùng ở nhiều lớp học hoặc trên sân trường, tất cả được quản lý từ một backend duy nhất. 

**Sự liên quan** : Khả năng mở rộng đảm bảo prototype không trở thành điểm yếu khi hệ thống phát triển về quy mô. 

**Ánh xạ tới yêu cầu:** NFREQ.7, NFREQ.8 

_**Bảng 21: Chiến lược Khả năng mở rộng**_ 

|**Hành động**|**Chiến lược**|
|---|---|
|Dùng mã thiết bị duy nhất cho mỗi thùng.<br>Tránh hardcode thông tin 1 thiết bị duy nhất.<br>Tách logic thiết bị khỏi logic dashboard.|Dùng JSON schema chuẩn. Thiết kế API xoay<br>quanh device ID và timestamp. Dùng<br>firmware để module hóa.|



## **3.1.4 Tính sẵn sàng và độ tin cậy** 

**Căn cứ:** Thùng rác cần hoạt động mọi lúc bất cứ khi nào cần kể cả khi mạng bị gián đoạn. 

**Động lực:** Mất điện, mất mạng hoặc lỗi cảm biến không được làm thùng ngừng hoạt động hoàn toàn làm mất dữ liệu phân loại. 

**Sự liên quan:** Thùng rác tự động không để mất sự kiện phân loại hay làm kẹt servo khi bị gián đoạn. 

**Ánh xạ tới yêu cầu:** NFREQ.9, NFREQ.10, NFREQ.11 

_**Bảng 22: Chiến lược Tính sẵn sàng và độ tin cậy**_ 

Trang 37 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Hành động**|**Chiến lược**|
|---|---|
|Giám sát trạng thái cảm biến liên tục. Phát<br>hiện servo bị kẹt. Duy trì vận hành cục bộ<br>khi không có mạng. Ghi log lỗi có thể và<br>không thể phục hồi.|Dùng trạng thái mặc định an toàn servo về vị trí<br>đóng hoặc dừng nhận rác khi phát hiện lỗi. Cung<br>cấp chế độ bảo trì có thể kích hoạt từ dashboard<br>hoặc thủ công tại thiết bị. . Xếp hàng telemetry<br>khi offline. Đặt lại vị trí servo khi khởi động.|



## **3.1.5 Độ tin cậy của AI** 

**Căn cứ:** Người dùng và người vận hành cần tin tưởng rằng hệ thống phân loại rác đúng và báo cáo trạng thái trung thực. 

**Động lực:** Phân loại sai, lỗi ẩn hoặc phản hồi không rõ ràng có thể làm giảm mức độ chấp nhận của người dùng và làm mất giá trị của hệ thống. 

**Sự liên quan:** Độ tin cậy đặc biệt quan trọng với hệ thống AI vì quyết định phân loại không hiển thị trực tiếp cho người dùng kiểm tra. 

**Ánh xạ tới yêu cầu:** NFREQ.12, NFREQ.13. 

_**Bảng 23: Chiến lược Độ tin cậy của AI**_ 

|**Hành động**|**Chiến lược**|
|---|---|
|Hiển thị kết quả phân loại và trạng thái hệ<br>thống lên đèn LED. Theo dõi phiên bản model<br>đang chạy. Ghi log kết quả phân loại để team<br>kỹ thuật đánh giá định kỳ.|Xác thực model trước khi triển khai. Ghi sự<br>kiện có thể truy vết theo device ID và<br>timestamp. Hiển thị rõ trạng thái lỗi hoặc độ<br>tin cậy thấp.|



## **3.1.6 Bảo mật** 

**Căn cứ:** Hệ thống cần bảo vệ cấu hình, dữ liệu telemetry và dashboard khỏi truy cập hoặc can thiệp bên ngoài. 

**Động lực:** Thiết bị kết nối mạng có thể bị cấu hình sai hoặc bị tấn công nếu không có kiểm soát truy cập và bảo mật mạng phù hợp. 

**Sự liên quan:** Bảo mật giúp bảo vệ an toàn cho toàn bộ dữ liệu cấu hình và dữ liệu thống kê của thùng rác. 

## **Ánh xạ tới yêu cầu:** NFREQ.14, NFREQ.15. 

_**Bảng 24: Chiến lược Bảo mật**_ 

|**Hành động**|**Chiến lược**|
|---|---|
|Xác thực người dùng dashboard. Bảo vệ<br>endpoint cấu hình. Dùng giao thức truyền<br>thông an toàn. Hạn chế truy cập vật lý vào<br>phần cứng.|Dùng phân quyền theo vai trò. Lưu thông tin<br>xác thực ngoài mã nguồn. Xác thực lệnh đến<br>từ dashboard trước khi firmware thực thi.<br>Kiểm soát quy trình cập nhật firmware.|



Trang 38 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

## **3.1.7 Quyền riêng tư** 

**Căn cứ:** Hệ thống cần giảm thiểu thu thập dữ liệu cá nhân và xử lý hình ảnh theo cách có trách nhiệm. 

**Động lực:** Thiết bị dùng camera đặt tại nơi công cộng có thể vô tình chụp thông tin cá nhân hoặc nhạy cảm của người dùng. 

**Sự liên quan:** Thiết kế hướng bảo mật quyền riêng tư là điều kiện cần để được chấp nhận triển khai tại không gian chung như trường học. 

**Ánh xạ tới yêu cầu:** NFREQ.16 

_**Bảng 25: Chiến lược Quyền riêng tư**_ 

|**Hành động**|**Chiến lược**|
|---|---|
|Xử lý hình ảnh cục bộ khi có thể. Xóa<br>hình ảnh tạm thời sau xử lý. Tránh chụp<br>khuôn mặt.|Cắt ảnh tập trung vào vật phẩm rác. Tắt lưu trữ<br>không cần thiết. Lập tài liệu chính sách lưu trữ. Ẩn<br>danh dataset dùng để cải thiện model.|



## **3.2 Yêu cầu chất lượng ngoài vận hành** 

## **3.2.1 Khả năng tiến hóa** 

**Căn cứ:** Hệ thống cần thích nghi khi có thêm loại rác mới, cảm biến mới, model AI mới hoặc môi trường triển khai mới. 

**Động lực:** Prototype có thể phát triển từ bản demo đơn giản thành hệ thống triển khai thực tế trên toàn khuôn viên trường. 

**Sự liên quan:** Khả năng tiến hóa ngăn prototype đầu tiên trở thành điểm yếu không thể mở rộng về sau. 

**Ánh xạ tới yêu cầu:** NFREQ.17, NFREQ.19 

_**Bảng 26: Chiến lược khả năng tiến hóa**_ 

|**Hành động**|**Chiến lược**|
|---|---|
|Xây dựng định nghĩa danh mục có thể cấu hình.<br>Đánh phiên bản cho cả firmware và model AI.<br>Lập tài liệu interface. Tách hiệu chỉnh phần<br>cứng (AI) khỏi logic nghiệp vụ.|Dùng firmware dạng module. Dùng data<br>schema có tài liệu rõ ràng. Dùng file model<br>AI có thể thay thế. Duy trì changelog.|



## **3.2.2 Khả năng mở rộng tính năng** 

**Căn cứ:** Hệ thống cần linh hoạt để thêm dịch vụ ngoài, kênh thông báo mới và danh mục rác bổ sung trong tương lai. 

**Động lực:** Các phát triển tương lai có thể bao gồm thông báo di động, tích điểm thưởng cho học sinh qua nhận diện khuôn mặt hoặc thêm lớp phân loại rác mới. 

**Sự liên quan:** Khả năng mở rộng tính năng tăng giá trị thực tế và giáo dục của dự án AIoT. 

Trang 39 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

## **Ánh xạ tới yêu cầu:** NFREQ.18 

_**Bảng 27: Chiến lược khả năng mở rộng tính năng**_ 

**Hành động Chiến lược** Định nghĩa API endpoint ổn định. Thiết kế Dùng giao diện REST hoặc MQTT. Dùng module thông báo có thể thay thế. Cho phép file cấu hình. Cung cấp tài liệu API. Tránh thêm ngăn mới qua cấu hình. Lập tài liệu ánh xạ phụ thuộc vendor cụ thể khi có thể. chân phần cứng. 

## **3.3 Danh sách yêu cầu phi chức năng** 

_**Bảng 28 Danh sách yêu cầu phi chức năng**_ 

|**ID #**|**Mô tả**|**Quan**<br>**tâm**|**Độ ưu**<br>**tiên**|**Miền**|
|---|---|---|---|---|
|NFREQ.1|Hệ thống hoàn thành phân loại trong<br>vòng ≤ 5 giây kể từ khi nhận ảnh hợp<br>lệ với độ chính xác 85% trở lên.|Hiệu<br>năng<br>&<br>Độ<br>tin<br>cậy AI|Bắt buộc|AI|
|NFREQ.2|Động cơ servo mở nắp trong vòng ≤ 5<br>giây sau khi mạch gửi lệnh đến khi<br>servo đạt góc mục tiêu.|Hiệu<br>năng|Bắt buộc|Thiết bị|
|NFREQ.3|Tự động quay nắp trở lại vị trí đóng<br>nắp ban đầu 5 giây  sau khi mở nắp<br>hoàn toàn để đảm bảo vệ sinh.|Hiệu<br>năng|Bắt buộc|Thiết bị|
|NFREQ.4|Ghi nhận dữ liệu từ cảm biến siêu âm<br>và cập nhật trạng thái đèn LED trong<br>≤ 0.5 giây sau khi nắp thùng đóng lại.|Hiệu<br>năng|Bắt buộc|Thiết bị|
|NFREQ.5|Quá trình Dashboard cập nhật và hiển<br>thị trạng thái thùng rác vừa được ghi<br>nhận ở mạch chính  không quá 5 giây.|Hiệu<br>năng|Bắt buộc|Firmware/Dashb<br>oard|
|NFREQ.6|Hệ thống lưu trữ dữ liệu tối thiểu 1<br>tháng (30 ngày), lưu cục bộ chỉ 24 giờ<br>khi mất mạng.|Lưu<br>trữ<br>dữ liệu|Bắt buộc|Database/Backe<br>nd|



Trang 40 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**ID #**|**Mô tả**|**Quan**<br>**tâm**|**Độ ưu**<br>**tiên**|**Miền**|
|---|---|---|---|---|
|NFREQ.7|Hỗ trợ tối thiểu 10 thiết bị đồng thời<br>mà không cần thay đổi kiến trúc trong<br>cùng một backend.|Khả năng<br>mở rộng|Nên có|Platform|
|NFREQ.8|Khi mất kết nối mạng firmware lưu<br>các sự kiện telemetry vào hàng đợi<br>trong RAM, tối đa 150 sự kiện hoặc<br>tối đa 24 giờ. Nếu hàng đợi đầy, hệ<br>thống loại bỏ sự kiện cũ nhất, giữ lại<br>các cái mới hơn, và ghi log số lượng<br>sự kiện đã mất. Khi mạng được khôi<br>phục, firmware tự động đồng bộ toàn<br>bộ dữ liệu còn trong hàng đợi lên<br>server theo thứ tự thời gian|Khả năng<br>mở rộng|Nên có|Firmware|
|NFREQ.9|Duy trì phân loại và mở nắp cục bộ<br>ngay khi backend không hoạt động<br>cùng cơ chế không mở nắp khi thùng<br>đầy.|Tính sẵn<br>sàng|Bắt buộc|Thiết bị|
|NFREQ.10|Khi có điện trở lại, firmware đưa servo<br>về vị trí đóng và kiểm tra phản hồi<br>cảm biến siêu âm 3 lần liên tiếp trong<br>vòng 5 giây trước khi tiếp tục nhận<br>rác. Nếu có giá trị không đúng trong<br>ngưỡng hợp lệ, thiết bị ghi log và gửi<br>cảnh báo lên dashboard và dừng nhận<br>rác.|Tính sẵn<br>sàng|Bắt buộc|Phần<br>cứng/Firmware|
|NFREQ.11|Phát hiện và báo cáo lỗi cảm biến hoặc<br>servo trong vòng 5 giây kể từ khi tín<br>hiệu bất thường.|Độ<br>tin<br>cậy|Bắt buộc|Thiết bị|
|NFREQ.12|Ghi log kết quả phân loại kèm phiên<br>bản model để team kỹ thuật đánh giá<br>định kỳ (1 lần/tuần).|Độ<br>tin<br>cậy AI|Bắt buộc|AI|
|NFREQ.13|Theo dõi phiên bản model và phiên<br>bản hiệu chỉnh.|Độ<br>tin<br>cậy AI|Nên có|Truy vết|



Trang 41 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**ID #**|**Mô tả**|**Quan**<br>**tâm**|**Độ ưu**<br>**tiên**|**Miền**|
|---|---|---|---|---|
|NFREQ.14|Yêu cầu xác thực cho các tính năng<br>quản trị.|Bảo mật|Bắt buộc|Dashboard|
|NFREQ.15|Tránh lưu thông tin xác thực trong mã<br>nguồn firmware.|Bảo mật|Bắt buộc|Firmware|
|NFREQ.16|Xóa hình ảnh tạm thời trong 2 giây sau<br>khi phân loại theo mặc định.|Quyền<br>riêng tư|Bắt buộc|AI/Camera|
|NFREQ.17|Hỗ trợ thay thế hoặc cập nhật model<br>AI, tối thiểu bằng cách nạp thủ công;<br>hỗ trợ cập nhật từ xa qua dashboard là<br>tùy chọn.|Khả năng<br>tiến hóa|Bắt buộc|AI|
|NFREQ.18|Cung cấp interface có tài liệu cho<br>dashboard và tích hợp API.|Khả năng<br>mở rộng<br>tính năng|Nên có|API|
|NFREQ.19|Lệnh cấu hình từ dashboard (cập nhật<br>ngưỡng, bật bảo trì) được firmware<br>nhận và áp dụng trong ≤ 7 giây kể từ<br>khi quản lý xác nhận trên dashboard,<br>với điều kiện thiết bị đang online.|Hiệu<br>năng|Nên có|Firmware/Dashb<br>oard|



## **4. Yêu cầu khác** 

## **4.1 Dữ liệu mô tả tối thiểu thiết bị cần gửi lên hệ thống** 

_**Bảng 29: Dữ liệu mô tả tối thiểu thiết bị cần gửi lên hệ thống**_ 

|**Thuộc Tính**|**Bắt**<br>**Buộc**|**Định nghĩa**|**Ví dụ**|
|---|---|---|---|
|Device ID|Có|Mã định danh duy nhất của thiết bị|STBIN_HCMUS_001|
|Location|Có|Vị trí lắp đặt hoặc tọa độ|Room<br>A301<br>/<br>10.7626,106.6822|
|Timestamp|Có|Thời điểm sự kiện theo chuẩn ISO<br>8601|2026-05-27T13:30:00Z|



Trang 42 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Thuộc Tính**|**Bắt**<br>**Buộc**|**Định nghĩa**|**Ví dụ**|
|---|---|---|---|
|Event Type|Có|Loại sự kiện|CLASSIFY,<br>FULL_ALERT,<br>ERROR,<br>MAINTENANCE|
|Waste Category|Có|Danh mục rác được dự đoán|RECYCLABLE|
|AI Confidence|Có|Điểm tin cậy của model từ 0.0 đến<br>1.0|0.92|
|Target<br>Compartment|Có|Ngăn được chọn bởi bộ điều khiển|Compartment 3|
|Fill Level Percent|Có|Phần trăm đầy của từng ngăn|Hữu cơ: 65,<br>Giấy: 80,<br>Nhựa: 80|
|Alert Threshold|Có|Ngưỡng đầy được cấu hình để kích<br>hoạt thông báo đầy|80%|
|Weight Kg|Không|Khối lượng rác đo được từ load cell|2.35|
|Firmware Version|Có|Phiên bản firmware đang chạy|v1.0.0|
|AI Model Version|Có|Phiên bản model phân loại|trashnet-tflite-v1|



## **4.2 Các định dạng dữ liệu được hỗ trợ** 

_**Bảng 30: Các định dạng dữ liệu được hỗ trợ**_ 

|**Loại MIME**|**Mô tả**|**Phần mở rộng**|**Mức độ**|
|---|---|---|---|
|application/json|Định dạng chính cho dữ liệu cảm<br>biến (telemetry) của thiết bị, các<br>yêu cầu API và phản hồi API|.json|Được hỗ trợ|
|text/csv|Định dạng xuất dữ liệu cho lịch<br>sử sự kiện và các báo cáo|.csv|Được hỗ trợ|
|application/xml|Định dạng tích hợp tùy chọn cho<br>các hệ thống bên ngoài|.xml|Tùy chọn|



Trang 43 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Loại MIME**|**Mô tả**|**Phần mở rộng**|**Mức độ**|
|---|---|---|---|
|image/jpeg|Định dạng ảnh tạm thời từ<br>camera dùng cho phân loại rác và<br>gỡ lỗi hệ thống|.jpg|Nội bộ|
|application/octet-stre<br>am|Gói cập nhật firmware hoặc mô<br>hình AI|.bin/.tflite|Dự kiến hỗ trợ|



Trang 44 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

## **5. Kết luận và kế hoạch phát triển tiếp theo** 

Tài liệu này trình bày bộ yêu cầu và kế hoạch phát triển cho prototype Smart Trash Bin AIoT trong môi trường trường học. Sản phẩm tập trung vào ba năng lực chính: hệ thống IoT phát hiện rác, đo mức đầy và mở đúng ngăn; AI nhận diện và phân loại rác; dashboard/thông báo giúp nhà trường theo dõi trạng thái thiết bị và dữ liệu phân loại. Trong giai đoạn phát triển tiếp theo, nhóm sẽ triển khai theo bốn phase trong 11 tuần, có kiểm thử thử nghiệm sau từng mục tiêu để bảo đảm mỗi phần được hoàn thiện trước khi tích hợp. Hai tuần cuối được ưu tiên cho kiểm thử ổn định, nâng cấp cơ khí, trang trí prototype, hoàn thiện slide, chuẩn bị demo script và tổng duyệt. 

_**Bảng 31: Kế hoạch phát triển dự án 11 tuần (Biểu đồ Gantt)**_ 

|**Mốc, sản phẩm bàn giao và hoạt động triển khai**|**Ngày dự kiến**|**Trạng thái**|
|---|---|---|
|**PHASE 1: Khởi tạo, đặc tả yêu cầu, nghiên cứu**<br>**công nghệ và thiết kế (SPEC 3 tuần)**<br>_Hoàn thành phần kế hoạch, spec, nghiên cứu công_<br>_nghệ AI, kiến trúc hệ thống, thiết bị, thiết kế sơ đồ và_<br>_chỉnh sửa đặc tả theo spec mới._|25/05/2026<br>-<br>12/06/2026|Hoàn thành|
|**Tìm kiếm, phân tích ý tưởng**<br>_Phân tích vấn đề phân loại rác trong trường học, xác_<br>_định hướng Smart Trash Bin AIoT và giá trị chính của_<br>_sản phẩm._|25/05/2026<br>-<br>27/05/2026|Hoàn thành|
|**Xác định phạm vi, mục đích, mục tiêu và lớp người**<br>**dùng**<br>_Chốt phạm vi hệ thống, mục đích, 3 mục tiêu theo_<br>_SMART và nhóm người dùng: học sinh, trường học,_<br>_nhân viên vận hành, quản trị viên._|27/05/2026<br>-<br>29/05/2026|Hoàn thành|
|**Lên kế hoạch 11 tuần và phân công task**<br>_Phân vai cho các phần: SRS/spec, AI nhận diện rác,_<br>_IoT/cơ khí, dashboard/thông báo, kiểm thử và thuyết_<br>_trình._|28/05/2026|Hoàn thành|
|**Mô tả sản phẩm, thiết bị/BOM và kiến trúc sơ bộ**<br>_Hoàn thiện mô tả thùng rác 3 ngăn, thiết bị chính, giá_<br>_tham khảo, ràng buộc phần cứng và kiến trúc AIoT ban_<br>_đầu._|29/05/2026<br>-<br>03/06/2026|Hoàn thành|



Trang 45 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Mốc, sản phẩm bàn giao và hoạt động triển khai**|**Ngày dự kiến**|**Trạng thái**|
|---|---|---|
|**Đặc tả use case, ranh giới hệ thống và functional**<br>**requirements**<br>_Đặc tả các use case chính theo 3 mục tiêu: phân loại_<br>_bằng AI, mở đúng ngăn/giám sát lượng rác,_<br>_dashboard/thông báo/thống kê._|03/06/2026<br>-<br>06/06/2026|Hoàn thành|
|**Nghiên cứu công nghệ AI, IoT, dashboard và tài**<br>**liệu liên quan**<br>_Tìm tài liệu về mô hình phân loại ảnh nhẹ,_<br>_ESP32-CAM/cảm biến/servo, giao tiếp Internet,_<br>_telemetry, lưu trữ dữ liệu và dashboard._|04/06/2026<br>-<br>09/06/2026|Hoàn thành|
|**Chỉnh sửa, cải thiện spec, sơ đồ và non-functional**<br>**requirements**<br>_Cập nhật mục tiêu mới, sửa cấu trúc tài liệu, cải thiện_<br>_sơ đồ hệ thống/action diagram, chuẩn hóa FR/NFR,_<br>_quyền riêng tư và tiêu chí kiểm thử._|10/06/2026<br>-<br>12/06/2026|Hoàn thành|
|**Slide/checkpoint W3 và chốt kế hoạch triển khai**<br>_Tổng hợp scope, mục đích, mục tiêu, use case, kiến_<br>_trúc, thiết bị và kế hoạch triển khai sau khi hoàn tất_<br>_tuần 3._|12/06/2026|Hoàn thành|
|**Giai đoạn 2 - Mục tiêu 1: AI nhận diện và phân loại**<br>**rác**<br>_Xây dựng pipeline camera - xử lý ảnh - model AI -_<br>_confidence threshold để phân loại hữu cơ/giấy/nhựa_<br>_với độ chính xác ≥ 85% và thời gian phản hồi ≤ 5 giây._|15/06/2026<br>-<br>26/06/2026|Hoàn thành|
|**Chuẩn bị dataset và tiêu chí phân loại hữu**<br>**cơ/giấy/nhựa**<br>_Thống nhất lớp nhãn, ảnh mẫu, điều kiện chụp trong_<br>_nhà và tiêu chí đánh giá phù hợp với vật phẩm rác_<br>_thường gặp ở trường học._|15/06/2026<br>-<br>16/06/2026|Hoàn thành|
|**Thiết lập pipeline camera, tiền xử lý ảnh và định**<br>**dạng input**<br>_Kết nối luồng ảnh từ camera, resize/normalize ảnh,_<br>_kiểm tra chất lượng ảnh và chuẩn hóa input cho mô_<br>_hình AI._|17/06/2026<br>-<br>18/06/2026|Hoàn thành|



Trang 46 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Mốc, sản phẩm bàn giao và hoạt động triển khai**|**Ngày dự kiến**|**Trạng thái**|
|---|---|---|
|**Huấn luyện/đánh giá model AI nhẹ và chọn ngưỡng**<br>**confidence**<br>_Train baseline model, đánh giá theo từng lớp rác, ghi_<br>_nhận lỗi dự đoán, tạo confusion matrix và chọn_<br>_threshold chấp nhận/từ chối kết quả._|19/06/2026<br>-<br>23/06/2026|Hoàn thành|
|**Kiểm thử mục tiêu 1: phân loại đúng/sai và thời**<br>**gian phản hồi**<br>_Kiểm thử độ chính xác ≥ 85%, thời gian phản hồi ≤ 5_<br>_giây, ảnh mờ, ánh sáng yếu và trường hợp confidence_<br>_thấp cần từ chối._|24/06/2026<br>-<br>26/06/2026|Hoàn thành|
|**Giai đoạn 3 - Mục tiêu 2: IoT, cảm biến và điều**<br>**khiển động cơ**<br>_Hoàn thiện luồng mạch chính nhận kết quả AI, mở_<br>_đúng ngăn trong ≤ 5 giây, đo mức đầy bằng cảm biến_<br>_siêu âm và cập nhật đèn trong ≤ 0.5 giây._|29/06/2026<br>-<br>10/07/2026|Hoàn thành|
|**Thiết kế mapping AI -> ngăn chứa và sơ đồ kết nối**<br>**thiết bị**<br>_Ánh xạ nhãn hữu cơ/giấy/nhựa sang 3 ngăn chứa, xác_<br>_định chân kết nối cho servo, cảm biến siêu âm, LED và_<br>_nguồn cấp._|29/06/2026<br>-<br>30/06/2026|Hoàn thành|
|**Chuẩn bị linh kiện, lắp mạch thử và kiểm tra nguồn**<br>_Lắp mạch thử, kiểm tra nguồn cấp servo, tín hiệu cảm_<br>_biến, kết nối camera/mạch chính và trạng thái an toàn_<br>_trước khi gắn vào mô hình._|01/07/2026<br>-<br>02/07/2026|Chưa bắt đầu|
|**Lập trình servo mở đúng ngăn và tự động đóng nắp**<br>_Điều khiển servo theo kết quả phân loại, hiệu chỉnh_<br>_góc mở/đóng, đảm bảo mở nắp trong ≤ 5 giây và tránh_<br>_kẹt cơ khí._|03/07/2026<br>-<br>06/07/2026|Chưa bắt đầu|
|**Lập trình cảm biến siêu âm, LED và kiểm thử mục**<br>**tiêu 2**<br>_Đo mức đầy sau khi nắp đóng, cập nhật LED trong ≤_<br>_0.5 giây, không mở ngăn đã đầy và kiểm thử lỗi cảm_<br>_biến/servo._|07/07/2026<br>-<br>10/07/2026|Chưa bắt đầu|



Trang 47 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Mốc, sản phẩm bàn giao và hoạt động triển khai**|**Ngày dự kiến**|**Trạng thái**|
|---|---|---|
|**Giai đoạn 4 - Mục tiêu 3: Dashboard, thông báo và**<br>**thống kê rác**<br>_Hoàn thiện lớp Internet/dashboard để cập nhật trạng_<br>_thái thùng vừa ghi nhận rác trong ≤ 5 giây, thông báo_<br>_đầy khi vượt ngưỡng đầy và lưu thống kê tối thiểu 30_<br>_ngày._|13/07/2026<br>-<br>24/07/2026|Chưa bắt đầu|
|**Thiết kế dữ liệu telemetry, API và cơ chế đồng bộ**<br>**Internet**<br>_Chuẩn hóa dữ liệu gửi lên gồm device_id, timestamp,_<br>_loại rác, ngăn chứa, phần trăm đầy, trạng thái thông_<br>_báo đầy và trạng thái kết nối._|13/07/2026<br>-<br>14/07/2026|Chưa bắt đầu|
|**Gửi thông báo thùng đầy và trạng thái thùng vừa**<br>**ghi nhận rác**<br>_Gửi event khi một ngăn vượt ngưỡng đầy, lưu tạm khi_<br>_mất mạng và tự động đồng bộ lại khi thiết bị có kết nối_<br>_Internet._|15/07/2026<br>-<br>17/07/2026|Chưa bắt đầu|
|**Dashboard trạng thái thùng, thông báo đầy và lần**<br>**cập nhật cuối**<br>_Hiển thị trạng thái kết nối, mức đầy từng ngăn, thông_<br>_báo đầy/lỗi và cập nhật thùng vừa ghi nhận rác trong ≤_<br>_5 giây._|20/07/2026<br>-<br>21/07/2026|Chưa bắt đầu|
|**Thống kê phân loại rác và kiểm thử mục tiêu 3**<br>_Tổng hợp thống kê theo ngày, loại rác và thùng; lưu dữ_<br>_liệu tối thiểu 30 ngày; kiểm thử lọc dữ liệu, thông báo_<br>_đầy và cập nhật dashboard._|22/07/2026<br>-<br>24/07/2026|Chưa bắt đầu|
|**Giai đoạn 5: Tích hợp, kiểm thử ổn định và hoàn**<br>**thiện demo (Test 2 tuần)**<br>_Tích hợp end-to-end 3 mục tiêu, kiểm thử ổn định, sửa_<br>_lỗi, nâng cấp prototype, hoàn thiện slide, kịch bản_<br>_demo và tổng duyệt._|27/07/2026<br>-<br>07/08/2026|Chưa bắt đầu|
|**Tích hợp tất cả 3 mục tiêu**<br>_Ghép luồng hoàn chỉnh: đưa rác vào vùng chờ -> AI_<br>_phân loại -> mở đúng ngăn -> đo mức đầy -> ghi_<br>_event -> dashboard cập nhật._|27/07/2026<br>-<br>29/07/2026|Chưa bắt đầu|



Trang 48 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|**Mốc, sản phẩm bàn giao và hoạt động triển khai**|**Ngày dự kiến**|**Trạng thái**|
|---|---|---|
|**Regression test, calibration và sửa lỗi**<br>_Chạy test lặp lại cho AI, cảm biến, servo, LED, kết nối_<br>_Internet và dashboard; calibration lại ngưỡng_<br>_confidence, góc servo và ngưỡng đầy._|30/07/2026<br>-<br>03/08/2026|Chưa bắt đầu|
|**Nâng cấp cơ khí, bố trí dây và trang trí prototype**<br>_Gia cố vỏ mô hình, bố trí dây, cố định camera/cảm_<br>_biến, kiểm tra an toàn cơ khí và hoàn thiện hình thức_<br>_prototype._|03/08/2026<br>-<br>04/08/2026|Chưa bắt đầu|
|**Hoàn thiện slide, demo script, phương án dự phòng**<br>**và tổng duyệt**<br>_Chuẩn bị slide cuối, kịch bản demo, dữ liệu minh họa,_<br>_phương án dự phòng khi lỗi mạng/AI/cơ khí và_<br>_acceptance test trước buổi trình bày._|05/08/2026<br>-<br>07/08/2026|Chưa bắt đầu|



_Ghi chú: Kế hoạch giữ nguyên khung 11 tuần. Tuần 1 - tuần 3 đã hoàn thành phần plan/spec/research công nghệ, kiến trúc, thiết bị, thiết kế và chỉnh sửa đặc tả. Từ tuần 4 trở đi triển khai lần lượt mục tiêu 1, mục tiêu 2, mục tiêu 3 và 2 tuần cuối cho tích hợp, kiểm thử ổn định, nâng cấp prototype, slide và tổng duyệt. Không thêm tính năng lớn sau tuần 9 để giữ thời gian test và hoàn thiện demo._ 

Trang 49 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

## **Phụ lục A - Bảng giá thiết bị chi tiết** 

Kiến trúc khuyến nghị cho prototype: ESP32-CAM xử lý camera/AI và có thể giao tiếp với Arduino/ESP32 để đọc cảm biến, điều khiển servo. Nếu cần giảm chi phí, nhóm có thể dùng ESP32-CAM cho bản nhẹ nhưng cần chấp nhận giới hạn về model và độ ổn định inference. 

_**Bảng 32: Kiến trúc phần cứng tổng quan (đơn vị: VNĐ)**_ 

|**Thiết bị đề xuất**|**Hình ảnh**|**Số**<br>**lượng**|**Giá tham**<br>**khảo**|**Thành tiền**|
|---|---|---|---|---|
|Kit phát triển Wi-Fi BLE ESP32<br>Camera ESP32-CAM Development<br>Board Ai-Thinker|acGe|1|225.000|225.000|
|Đế nạp chương trình ESP32-CAM<br>USB Programming Adapter|oS.|1|32.000|32.000|
|Động cơ RC Servo 9G 180°||3|42.000|126.000|
|Cảm biến siêu âm HC-SR04|J<br>oFa|4|27.000|108.000|
|Mạch Mtiny Power (Support USB<br>Power Bank)|Smmrig|1|55.000|55.000|
|Dây đực - cái (40 sợi)||1|30.000|30.000|
|Dây cái - cái (40 sợi)||1|30.000|30.000|
|Cáp Micro USB|es)<br>\—4|1|27.000|27.000|
|Cáp USB-C||1|35.000|35.000|



Trang 50 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

|Bộ 3 loại LED màu 5mm thông dụng|eA|1|3.000|3.000|
|---|---|---|---|---|
|Vật liệu vỏ thùng (Bìa carton<br>60cmx30cm)||1|70.000|70.000|
|**Tổng kinh phí**||||**741.000**|



## ~~LT~~ **Phụ lục B - PEAS và so sánh giải pháp Phụ lục B.1 - PEAS** 

_**Bảng 33: Phân tích PEAS cho Smart Trash Bin**_ 

|**PEAS**|**Nội dung cho Smart Trash Bin**|
|---|---|
|Performance Measure|Phân loại đúng, không tràn rác, ít lỗi servo/cảm biến, dashboard cập<br>nhật đúng.|
|Environment|Trường tiểu học/mẫu giáo, lớp học, hành lang, khu vực có nhiều học<br>sinh, ánh sáng trong nhà.|
|Actuators|Servo mở nắp/ngăn, LED.|
|Sensors|Camera, cảm biến siêu âm, cảm biến hiện diện nếu cần.|



## **Phụ lục B.2 - So sánh giải pháp** 

_**Bảng 34: So sánh các giải pháp quản lý rác**_ 

|**Tiêu chí**|**Thùng rác thường**|**Thùng có nhãn phân loại**|**Smart Trash Bin AIoT**|
|---|---|---|---|
|Hỗ trợ học sinh|Không hỗ trợ|Có nhãn nhưng vẫn phải<br>tự đoán|AI gợi ý/mở đúng ngăn|
|Độ đo lường|Không có dữ liệu|Không có dữ liệu tự động|Có event, mức đầy,<br>thống kê|
|Vận hành|Phải kiểm tra thủ<br>công|Phải kiểm tra thủ công|Có thông báo đầy thùng|
|Giá trị giáo dục|Thấp|Trung bình|Cao vì có phản hồi tức<br>thời|
|Độ phức tạp|Rất thấp|Thấp|Cao hơn, cần bảo trì<br>sensor/AI|



Trang 51 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

## **Phụ lục C - Thiết kế demo (prototype)** 

Tổng quan các thiết kế UI, mockup, 3D của hệ thống, xem chi tiết cách sử dụng hệ thống tại Link video demo. 

_Hình 14. Thiết kế mẫu hệ thống_ 

_Hình 15. Giao diện dashboard giám sát trạng thái hệ thống_ 

Trang 52 

Tài liệu đặc tả yêu cầu phần mềm cho hệ thống Thùng rác thông minh AIoT 

_Hình 16. Giao diện thống kê_ 

_Hình 17. Giao diện cấu hình hệ thống_ 

Trang 53 

