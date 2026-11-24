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
 console.log('Shot screen: native-disabled form absent; explicit portrait/architecture/landscape diagrams pass.');
})().catch(e=>{console.error(e);process.exitCode=1});
