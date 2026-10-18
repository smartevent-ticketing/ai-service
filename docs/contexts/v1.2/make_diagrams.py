from pathlib import Path
from graphviz import Digraph
ROOT=Path(__file__).resolve().parent / "figures"
ROOT.mkdir(exist_ok=True)

def base(name, rankdir='TB'):
    g=Digraph(name, format='png')
    g.attr(rankdir=rankdir, bgcolor='white', pad='0.25', nodesep='0.45', ranksep='0.55')
    g.attr('node', shape='box', style='rounded,filled', fontname='DejaVu Sans', fontsize='11', color='#5B6470', fillcolor='#F5F7FA', fontcolor='#1F2937', margin='0.16,0.10')
    g.attr('edge', color='#64748B', arrowsize='0.8', penwidth='1.2', fontname='DejaVu Sans', fontsize='9')
    return g

# 1 architecture
g=base('architecture')
g.node('user','Người dùng')
g.node('web','Next.js Chat UI\nEvent/Ticket cards')
g.node('bff','Chat BFF\nAuth • rate limit • SSE')
g.node('ai','FastAPI AI Service', fillcolor='#E8F1FF', color='#3B82F6')
g.node('slm','SLM 1.5B–1.7B + QLoRA\nIntent • slot • state delta')
g.node('tods','TODS / Policy Engine\nState • rules • GET-only')
g.node('rag','RAG\nTri thức đã duyệt')
g.node('jev','JEV (tùy chọn)\nRouter / evidence evaluator')
g.node('opt','Ticket Optimizer\nHard filter • ranking • alternatives')
g.node('tools','READ-ONLY Tools\nGET only • schema • timeout')
g.node('be','Spring Boot Backend\nNguồn sự thật nghiệp vụ', fillcolor='#ECFDF5', color='#10B981')
g.node('db','PostgreSQL\nBusiness state')
g.node('state','Chat DB / Redis\nConversation state')
g.edges([('user','web'),('web','bff'),('bff','ai'),('ai','slm'),('slm','tods'),('tods','rag'),('tods','jev'),('tods','opt'),('tods','tools'),('tools','be'),('be','db'),('ai','state')])
g.edge('rag','tods', label='evidence')
g.edge('opt','tods', label='ranked options')
g.render(str(ROOT/'01_kien_truc_tong_the'), cleanup=True)

# 2 request flow
g=base('request_flow', rankdir='LR')
for nid,label,color in [
('msg','Tin nhắn người dùng',None),('under','SLM hiểu yêu cầu',None),('merge','Validate + Merge state',None),('policy','Policy Engine', '#E8F1FF'),('branch','Phân loại tác vụ',None),('rag','RAG',None),('api','Backend Tools',None),('opt','Ticket Optimizer',None),('valid','Kiểm tra evidence / revalidate',None),('resp','Phản hồi có căn cứ', '#ECFDF5')]:
    attrs={}
    if color: attrs['fillcolor']=color
    g.node(nid,label,**attrs)
g.edges([('msg','under'),('under','merge'),('merge','policy'),('policy','branch')])
g.edge('branch','rag',label='FAQ/policy')
g.edge('branch','api',label='data thật')
g.edge('branch','opt',label='recommend')
g.edges([('rag','valid'),('api','valid'),('opt','valid'),('valid','resp')])
g.render(str(ROOT/'02_luong_xu_ly_hoi_thoai'), cleanup=True)

# 3 source of truth
g=base('truth', rankdir='TB')
g.node('model','SLM / LLM / JEV\nDự đoán ngữ nghĩa', fillcolor='#FFF7ED', color='#F59E0B')
g.node('policy','Policy + Rules\nQuyết định hành động hợp lệ')
g.node('tool','GET-only Tool Adapter\nDeny business writes')
g.node('backend','Spring Boot\nAuthorization + business invariants', fillcolor='#ECFDF5', color='#10B981')
g.node('pg','PostgreSQL\nNguồn sự thật cuối cùng', fillcolor='#ECFDF5', color='#10B981')
g.node('redis','Redis\nCache/counter/rate limit')
g.edge('model','policy',label='đề xuất')
g.edge('policy','tool',label='cho phép')
g.edge('tool','backend',label='GET only')
g.edge('backend','pg',label='business reads')
g.edge('backend','redis',style='dashed',label='dữ liệu dẫn xuất')
g.render(str(ROOT/'03_nguon_su_that_va_kiem_soat'), cleanup=True)

# 4 optimizer
g=base('optimizer', rankdir='LR')
g.node('constraints','Yêu cầu người dùng\nquantity • budget • seat preference')
g.node('snapshot','Backend snapshot\nphases • inventory • seats')
g.node('candidates','Sinh ứng viên')
g.node('hard','Lọc ràng buộc cứng\nstatus • limit • inventory • auth', fillcolor='#FEE2E2', color='#EF4444')
g.node('soft','Chấm điểm ràng buộc mềm\nprice • seat proximity • preference')
g.node('rank','Xếp hạng')
g.node('alt','Phương án chính + thay thế', fillcolor='#ECFDF5', color='#10B981')
g.edge('constraints','candidates')
g.edge('snapshot','candidates')
g.edges([('candidates','hard'),('hard','soft'),('soft','rank'),('rank','alt')])
g.render(str(ROOT/'04_ticket_optimizer'), cleanup=True)

# 5 implementation roadmap
g=base('roadmap', rankdir='LR')
weeks=[
('w1','Tuần 1\nFoundation\nOntology + contracts'),
('w2','Tuần 2\nTODS\nState + policy'),
('w3','Tuần 3\nTools + UI\nE2E slice'),
('w4','Tuần 4\nDataset\nBaseline'),
('w5','Tuần 5\nQLoRA\nEvaluation'),
('w6','Tuần 6\nOptimizer + RAG'),
('w7','Tuần 7\nJEV + Security'),
('w8','Tuần 8\nE2E + Load\nReport')]
for nid,label in weeks:g.node(nid,label)
for a,b in zip([x[0] for x in weeks[:-1]],[x[0] for x in weeks[1:]]):g.edge(a,b)
g.render(str(ROOT/'05_lo_trinh_8_tuan'), cleanup=True)

# 6 agent protocol
g=base('agent', rankdir='LR')
steps=[('r','Đọc context\n+ AGENTS'),('s','Xác định repo/branch\n+ working tree'),('e','Đọc code/API/test\nthật'),('p','Lập change plan'),('c','Code nhỏ\n+ typed contracts'),('t','Chạy tests/evals'),('a','Audit security\n+ docs drift'),('o','Báo cáo evidence')]
for nid,label in steps:g.node(nid,label)
for a,b in zip([x[0] for x in steps[:-1]],[x[0] for x in steps[1:]]):g.edge(a,b)
g.render(str(ROOT/'06_quy_trinh_ai_agent'), cleanup=True)
print('done')

# 7 read-only contract
g=base('read_only',rankdir='LR')
g.node('chat','SmartEvent AI Chatbot\nIntent • Analyze • Recommend',fillcolor='#E8F1FF',color='#3B82F6')
g.node('gate','ReadOnlyBusinessToolExecutor\nGET allowlist • Auth • Validation',fillcolor='#ECFDF5',color='#10B981')
g.node('backend','Spring Boot\nRead endpoints only')
g.node('block','POST / PUT / PATCH / DELETE\nDENIED / NO NETWORK CALL',fillcolor='#FEE2E2',color='#EF4444')
g.node('nav','NAVIGATE_TO_BOOKING\nUI link only')
g.node('ui','User self-service UI\nUser performs transactions')
g.edge('chat','gate',label='read')
g.edge('gate','backend',label='GET')
g.edge('chat','block',label='any mutation')
g.edge('chat','nav',label='suggest link')
g.edge('nav','ui',label='user clicks')
g.render(str(ROOT/'07_read_only_boundary'),cleanup=True)
print('read-only diagram done')
