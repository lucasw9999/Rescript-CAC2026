/** Rescript's reusable primitive-built cast. Three.js r180, bundled locally.
 * createCharacter(id) returns an independent THREE.Group; +Z is the face.
 * Export and website use these exact models. Units are intentionally shared.
 */
import * as THREE from './vendor/three.module.min.js';
export { THREE };
export const CAST = Object.freeze([
  {id:'pip',name:'Pip',role:'Transcribe',color:'#0a6cff',idle:'listening nod'},
  {id:'kit',name:'Kit',role:'Rewrite',color:'#ff827c',idle:'thoughtful tilt'},
  {id:'echo',name:'Echo',role:'Voice sample / Re-voice',color:'#a894ed',idle:'soft speaking sway'},
  {id:'tempo',name:'Tempo',role:'Retime',color:'#ffcb55',idle:'gentle metronome rock'},
  {id:'scout',name:'Scout',role:'Check',color:'#72d7b2',idle:'reassuring nod'}
]);
const mat = color => new THREE.MeshPhysicalMaterial({color,roughness:.3,metalness:0,clearcoat:.4,clearcoatRoughness:.3});
function mesh(geometry,material,parent,x=0,y=0,z=0){const m=new THREE.Mesh(geometry,material);m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;}
function ball(parent,material,x,y,z,sx,sy=sx,sz=sx){const m=mesh(new THREE.SphereGeometry(1,32,24),material,parent,x,y,z);m.scale.set(sx,sy,sz);return m;}
function capsule(parent,material,x,y,z,r=.15,length=.3){return mesh(new THREE.CapsuleGeometry(r,length,8,20),material,parent,x,y,z);}
function roundBox(w,h,d,r=.15){const s=new THREE.Shape(),x=-w/2+r,y=-h/2+r,W=w-2*r,H=h-2*r;s.moveTo(x,y-r);s.lineTo(x+W,y-r);s.quadraticCurveTo(x+W+r,y-r,x+W+r,y);s.lineTo(x+W+r,y+H);s.quadraticCurveTo(x+W+r,y+H+r,x+W,y+H+r);s.lineTo(x,y+H+r);s.quadraticCurveTo(x-r,y+H+r,x-r,y+H);s.lineTo(x-r,y);s.quadraticCurveTo(x-r,y-r,x,y-r);const g=new THREE.ExtrudeGeometry(s,{depth:d-2*r,bevelEnabled:true,bevelSegments:5,steps:1,bevelSize:r,bevelThickness:r,curveSegments:12});g.translate(0,0,-(d-2*r)/2);return g;}
function rod(parent,material,from,to,r=.04){const a=new THREE.Vector3(...from),b=new THREE.Vector3(...to);const m=capsule(parent,material,...a.clone().add(b).multiplyScalar(.5).toArray(),r,a.distanceTo(b));m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),b.sub(a).normalize());return m;}
function ring(parent,material,x,y,z,r=.2,t=.04,arc=Math.PI*2){return mesh(new THREE.TorusGeometry(r,t,12,48,arc),material,parent,x,y,z);}
export function createCharacter(id){
 const spec=CAST.find(c=>c.id===id);if(!spec)throw new Error('Unknown Rescript character: '+id);
 const g=new THREE.Group();g.name=spec.name;g.userData={...spec};const color=mat(spec.color),ink=mat('#17253d'),white=mat('#ffffff'),pale=mat('#f5f9ff'),pink=mat('#ffb8b5');
 if(id==='kit')mesh(roundBox(1.12,1.22,.85,.2),color,g,0,.05,0);
 else if(id==='tempo') {ring(g,color,0,.1,0,.53,.23);const disk=mesh(new THREE.CylinderGeometry(.5,.5,.23,48),pale,g,0,.1,.07);disk.rotation.x=Math.PI/2;capsule(g,color,0,.93,0,.13,.12);}
 else if(id==='scout')ball(g,color,0,.05,0,.66,.68,.53);
 else {const b=capsule(g,color,0,.06,0,.52,id==='echo'?.48:.4);b.scale.z=.87;}
 for(const side of [-1,1]){
   ball(g,color,side*.28,-.83,.09,.23,.15,.3);
   const arm=capsule(g,color,side*.68,-.18,0,.12,.27);arm.rotation.z=side*.6;
   ball(g,color,side*.76,-.34,.12,.16);
   ball(g,white,side*.215,.3,.48,.185,.22,.12);
   ball(g,ink,side*.205,.29,.586,.085,.116,.047);
   ball(g,white,side*.205-.025,.33,.63,.027);
   ball(g,pink,side*.38,.02,.45,.086,.042,.025);
 }
 const smile=ring(g,ink,0,.02,.51,.105,.018,Math.PI);smile.rotation.z=Math.PI;
 if(id==='pip'){
   ring(g,ink,0,.37,0,.62,.075,Math.PI);
   for(const s of [-1,1]){const pad=capsule(g,ink,s*.59,.24,.01,.17,.16);pad.scale.z=.8;ball(g,white,s*.72,.24,.01,.045,.12,.09);}
   const note=mesh(roundBox(.43,.5,.1,.06),white,g,.88,-.26,.3);note.rotation.z=-.15;
   for(let i=0;i<3;i++)rod(g,color,[.76,-.15-i*.08,.38],[.99,-.15-i*.08,.38],.014);
 }
 if(id==='kit'){
   const pencil=new THREE.Group();g.add(pencil);pencil.position.set(.85,-.1,.27);pencil.rotation.z=-.35;
   capsule(pencil,mat('#ffcb55'),0,0,0,.075,.6);capsule(pencil,pink,0,.4,0,.08,.04);
   const tip=mesh(new THREE.ConeGeometry(.075,.18,20),ink,pencil,0,-.43,0);tip.rotation.z=Math.PI;
   ball(g,color,-.35,.76,0,.14,.18,.13);ball(g,color,-.16,.75,0,.13,.14,.12);
 }
 if(id==='echo'){
   for(let i=0;i<3;i++)capsule(g,white,(i-1)*.15,-.32,.49,.035,i===1?.2:.08);
   const mic=new THREE.Group();g.add(mic);mic.position.set(.85,-.13,.23);capsule(mic,ink,0,-.17,0,.045,.3);capsule(mic,pale,0,.11,0,.13,.12);
   for(const s of [-1,1])rod(mic,ink,[s*.1,.1,.1],[s*.1,-.05,.1],.012);
 }
 if(id==='tempo'){
   for(const s of [-1,1]){const bell=ball(g,color,s*.48,.79,0,.23,.13,.2);bell.rotation.z=s*-.5;}
   rod(g,ink,[0,-.17,.255],[0,-.35,.255],.025);rod(g,ink,[0,-.35,.255],[.17,-.35,.255],.025);
 }
 if(id==='scout'){
   for(const s of [-1,1])ring(g,ink,s*.215,.3,.61,.22,.032);
   rod(g,ink,[-.03,.32,.61],[.03,.32,.61],.028);
   const board=new THREE.Group();g.add(board);board.position.set(-.8,-.26,.27);board.rotation.z=.12;mesh(roundBox(.43,.52,.12,.055),white,board);mesh(roundBox(.19,.1,.08,.025),ink,board,0,.26,.07);
   rod(board,mat('#16805d'),[-.12,-.02,.1],[-.025,-.12,.1],.025);rod(board,mat('#16805d'),[-.025,-.12,.1],[.13,.1,.1],.025);
 }
 return g;
}
export function setupLighting(scene){scene.add(new THREE.HemisphereLight('#ffffff','#aabed6',2.4));const key=new THREE.DirectionalLight('#fff8f3',4);key.position.set(-3,6,7);scene.add(key);const fill=new THREE.DirectionalLight('#d1e8ff',2);fill.position.set(4,2,-3);scene.add(fill);}
export function createRenderer(canvas,{exporting=false}={}){const renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:true,preserveDrawingBuffer:exporting,powerPreference:'low-power'});renderer.setPixelRatio(exporting?1:Math.min(devicePixelRatio||1,2));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.12;renderer.setClearColor(0xffffff,0);return renderer;}
export function renderCharacterPNG(id,size=512){const canvas=document.createElement('canvas');const renderer=createRenderer(canvas,{exporting:true});renderer.setSize(size,size,false);const scene=new THREE.Scene();setupLighting(scene);const character=createCharacter(id);character.rotation.y=-.15;scene.add(character);const camera=new THREE.OrthographicCamera(-1.42,1.42,1.42,-1.42,.1,30);camera.position.set(0,1.1,7);camera.lookAt(0,.1,0);renderer.render(scene,camera);const data=canvas.toDataURL('image/png');scene.traverse(o=>{o.geometry?.dispose();if(o.material){(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose());}});renderer.dispose();return data;}
export function mountCrew(canvas,{onReady=()=>{},onError=()=>{}}={}){
 let renderer;try{renderer=createRenderer(canvas);}catch(error){onError(error);return null;}
 const scene=new THREE.Scene();setupLighting(scene);const camera=new THREE.OrthographicCamera(-4.1,4.1,3,-3,.1,30);camera.position.set(0,2.8,10);camera.lookAt(0,0,0);
 const root=new THREE.Group();scene.add(root);const placements=[[-2.5,-.04,.05],[-1.3,.12,-.2],[0,.3,.2],[1.3,.08,-.2],[2.5,-.02,0]];
 const cast=CAST.map((c,i)=>{const model=createCharacter(c.id);model.position.set(...placements[i]);model.scale.setScalar(.92);model.rotation.y=(2-i)*.06;root.add(model);return model;});
 const stage=mesh(new THREE.CylinderGeometry(3.5,3.5,.16,80),mat('#dcecff'),scene,0,-1.13,-.1);stage.scale.z=.48;
 const wave=new THREE.Group();scene.add(wave);wave.position.set(0,-1.63,.1);for(let i=0;i<27;i++){const h=.07+Math.abs(Math.sin(i*1.7))*.13;const bar=capsule(wave,mat(i%4===0?'#0a6cff':'#a9c7f0'),(i-13)*.2,0,0,.025,h);bar.userData.base=h;}
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');let frame=0,time=0,last=0,visible=true,paused=false,lost=false;
 const draw=()=>renderer.render(scene,camera);
 function resize(){const w=canvas.clientWidth,h=canvas.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);const aspect=w/h,halfW=Math.max(3.75,2.55*aspect),halfH=halfW/aspect;camera.left=-halfW;camera.right=halfW;camera.top=halfH;camera.bottom=-halfH;camera.updateProjectionMatrix();draw();}
 function animate(now){frame=0;if(document.hidden||!visible||paused||lost)return;const dt=Math.min((now-last)/1000||0,.05);last=now;time+=dt;cast.forEach((m,i)=>{m.position.y=placements[i][1]+Math.sin(time*1.5+i)*.055;m.rotation.z=Math.sin(time*1.15+i)*.035;});wave.children.forEach((b,i)=>b.scale.y=1+Math.sin(time*2.5+i*.65)*.2);draw();if(!reduced.matches)frame=requestAnimationFrame(animate);}
 function refresh(){cancelAnimationFrame(frame);frame=0;last=0;if(!document.hidden&&visible&&!lost){draw();if(!reduced.matches&&!paused)frame=requestAnimationFrame(animate);}}
 const observer=new ResizeObserver(resize);observer.observe(canvas);const intersection=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;refresh();});intersection.observe(canvas);
 const visibility=()=>refresh(),change=()=>{if(reduced.matches){cast.forEach((m,i)=>{m.position.y=placements[i][1];m.rotation.z=0;});}refresh();};document.addEventListener('visibilitychange',visibility);reduced.addEventListener('change',change);
 const loss=e=>{e.preventDefault();lost=true;cancelAnimationFrame(frame);onError(new Error('3D display interrupted; still characters remain available.'));},restore=()=>{lost=false;resize();onReady();refresh();};canvas.addEventListener('webglcontextlost',loss);canvas.addEventListener('webglcontextrestored',restore);
 resize();onReady();refresh();return {setPaused(value){paused=value;refresh();},pose(mode){root.rotation.y=mode==='after'?-.04:.04;draw();},dispose(){cancelAnimationFrame(frame);observer.disconnect();intersection.disconnect();document.removeEventListener('visibilitychange',visibility);reduced.removeEventListener('change',change);canvas.removeEventListener('webglcontextlost',loss);canvas.removeEventListener('webglcontextrestored',restore);scene.traverse(o=>{o.geometry?.dispose();if(o.material)(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose());});renderer.dispose();}};
}
