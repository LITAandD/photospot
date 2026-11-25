const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),{act,create}=require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT=true;
const tags=names=>Object.fromEntries(names.map(n=>[n,n]));
const UI=tags(['Body','Button','Card','Chip','ErrorBox','Field','Muted','Screen','Title']);
function load(file,stubs){const mod={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'..',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:mod,exports:mod.exports,URLSearchParams,Set,Map,Date,Promise,process:{env:{}},require:n=>{if(n==='react'||n==='react/jsx-runtime')return require(n);if(n in stubs)return stubs[n];throw Error(n)}});return mod.exports;}
(async()=>{
 const helpers=load('src/shot-guide.ts',{});
 const rn={...tags(['ActivityIndicator','Linking','View','Image','Text']),Platform:{OS:'ios'}};
 const screen=load('app/today-shot.tsx',{'react-native':rn,'expo-router':{useLocalSearchParams:()=>({}),useRouter:()=>({push(){},setParams(){}})},'@/api':{DEMO:false,today:()=> '2026-11-24'},'@/analytics':{track(){throw Error('must not track')}},'@/calendar':{validCalendarDate:()=>false},'@/hooks':{useDocumentTitle(){},useAsync:()=>({data:null,loading:false,error:null})},'@/components/ui':UI,'@/components/calendar-field':{CalendarField:'CalendarField'},'@/components/shot-card':{ShotCard:'ShotCard'},'@/shot-guide':helpers,'@/share':{}}).default;
 let tree;await act(async()=>{tree=create(React.createElement(screen))});assert.equal(tree.root.findAllByType('Chip').length,0);assert.equal(tree.root.findAllByType('Field').length,0);assert.match(JSON.stringify(tree.toJSON()),/공개 웹에서 준비 중/);await act(async()=>tree.unmount());
 const {ShotDiagram}=load('src/components/shot-card.tsx',{'react-native':rn,'react-native-svg':{__esModule:true,default:'Svg',...tags(['Rect','Path','Circle','Line','G','Text'])},'./ui':UI,'@/shot-guide':helpers,'@/theme':{colors:{},fonts:{}}});
 for(const subject of ['portrait','architecture','landscape']){
  await act(async()=>{tree=create(React.createElement(ShotDiagram,{shot:{framing:'검증 구도',pin:{bearing_deg:45},visual:{composition:{subject,orientation:'portrait',subject_x:1/3}}}}))});
  assert.equal(tree.root.findAll(n=>n.props.testID===`diagram-${subject}`).length,1);assert.match(tree.root.findByType('View').props.accessibilityLabel,/북동쪽/);await act(async()=>tree.unmount());
 }
 // Exercise the real screen and card together: local editing must not redraw the SVG,
 // but completion and a different result must still update the card and callbacks.
 let drawings=0, shown;
 const cards=load('src/components/shot-card.tsx',{'react-native':rn,'react-native-svg':{__esModule:true,default:props=>{drawings++;return React.createElement('Svg',props)},...tags(['Rect','Path','Circle','Line','G','Text'])},'./ui':UI,'@/shot-guide':helpers,'@/theme':{colors:{},fonts:{}}});
 const params={date:'2026-11-25',review:'open'};
 const shot={cut_id:'test-cut-a',title:'검토 예시 A',place_name:'합성 장소',pin:{bearing_deg:45},visual:{kind:'diagram',composition:{subject:'portrait',orientation:'portrait',subject_x:1/3}},place_hours:[],cut_hours:[],sources:[]};
 shown={primary:shot,mode:'review',goal_counts:{portrait:1,architecture:1,landscape:0},excluded:[],request_key:helpers.shotParams({date:params.date,party:'',goal:'',time:'',cut:'',review:'open'}).toString()};
 const active=load('app/today-shot.tsx',{'react-native':rn,'expo-router':{useLocalSearchParams:()=>params,useRouter:()=>({push(){},setParams(){}})},'@/api':{DEMO:true,today:()=>params.date},'@/analytics':{track(){throw Error('review must not track')}},'@/calendar':{validCalendarDate:()=>true},'@/hooks':{useDocumentTitle(){},useAsync:()=>({data:shown,loading:false,error:null})},'@/components/ui':UI,'@/components/calendar-field':{CalendarField:'CalendarField'},'@/components/shot-card':cards,'@/shot-guide':helpers,'@/share':{}}).default;
 await act(async()=>{tree=create(React.createElement(active))});
 const button=title=>tree.root.findAllByType('Button').find(n=>n.props.title===title);
 const before=drawings;
 await act(async()=>button('조건 바꾸기').props.onPress());
 for(const value of ['1','15','15:','15:3','15:30'])await act(async()=>tree.root.findByType('Field').props.onChange(value));
 assert.equal(drawings,before,'editing five characters must not redraw an unchanged guide');
 await act(async()=>button('카카오맵으로 길찾기').props.onPress());
 assert.equal(drawings,before,'an action notice must not redraw the guide');
 await act(async()=>button('안내대로 찍었어요').props.onPress());
 assert.equal(button('확인했어요 · 감사합니다').props.disabled,true);assert.ok(drawings>before);
 shown={...shown,primary:{...shot,cut_id:'test-cut-b',title:'검토 예시 B'}};
 await act(async()=>tree.update(React.createElement(active)));
 assert.equal(button('안내대로 찍었어요').props.disabled,false);
 await act(async()=>button('안내대로 찍었어요').props.onPress());
 assert.equal(button('확인했어요 · 감사합니다').props.disabled,true);
 await act(async()=>tree.unmount());
 console.log('Shot screen: native gating, diagrams, zero card redraws during editing/notices, completion and changed-result callbacks pass.');
})().catch(e=>{console.error(e);process.exitCode=1});
