const API = "http://127.0.0.1:8000";
const crops = ["Tomato","Potato","Onion","Wheat","Rice","Cauliflower","Cabbage","Brinjal","Chilli","Mango","Banana"];
const locations = ["Kolkata","Howrah","Hooghly","Nadia","Burdwan"];
const cropEmoji = {Tomato:"🍅",Potato:"🥔",Onion:"🧅",Wheat:"🌾",Rice:"🍚",Cauliflower:"🥦",Cabbage:"🥬",Brinjal:"🍆",Chilli:"🌶️",Mango:"🥭",Banana:"🍌"};
let user = JSON.parse(localStorage.getItem("kdUser") || "null");
let authMode = "login";
function fillSelect(id, values){document.getElementById(id).innerHTML=values.map(v=>`<option>${v}</option>`).join("")}
["priceCrop","demandCrop","sellCrop"].forEach(id=>fillSelect(id,crops));
["priceLocation","demandLocation","sellLocation"].forEach(id=>fillSelect(id,locations));
function showAuth(){document.getElementById("authModal").classList.remove("hidden");setMode("login")}
function hideAuth(){document.getElementById("authModal").classList.add("hidden")}
function setMode(mode){authMode=mode;document.getElementById("loginTab").classList.toggle("active",mode==="login");document.getElementById("registerTab").classList.toggle("active",mode==="register");document.getElementById("nameWrap").style.display=mode==="register"?"block":"none";document.getElementById("roleWrap").style.display=mode==="register"?"block":"none";document.getElementById("authSubmit").textContent=mode==="login"?"Login":"Create account";document.getElementById("authMessage").textContent=""}
function updateAuth(){document.getElementById("authArea").innerHTML=user?`<span class="message">Hi, ${escapeHtml(user.name)}</span> <button class="btn ghost" onclick="logout()">Logout</button>`:`<button class="btn ghost" onclick="showAuth()">Login / Register</button>`}
function logout(){user=null;localStorage.removeItem("kdUser");updateAuth()}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
async function submitAuth(){
 const body={email:document.getElementById("authEmail").value,password:document.getElementById("authPassword").value};
 if(authMode==="register"){body.name=document.getElementById("authName").value;body.role=document.getElementById("authRole").value}
 try{const r=await fetch(API+(authMode==="login"?"/api/login":"/api/register"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.detail||"Request failed");user=d;localStorage.setItem("kdUser",JSON.stringify(user));updateAuth();hideAuth()}catch(e){document.getElementById("authMessage").textContent=e.message}
}
async function predict(kind){
 const prefix=kind==="price"?"price":"demand", result=document.getElementById(prefix+"Result");
 const body={crop:document.getElementById(prefix+"Crop").value,season:document.getElementById(prefix+"Season").value,location:document.getElementById(prefix+"Location").value,month:Number(document.getElementById(prefix+"Month").value),rainfall_mm:Number(document.getElementById(prefix+"Rain").value),temperature_c:Number(document.getElementById(prefix+"Temp").value)};
 result.textContent="Calculating estimate…";
 try{const r=await fetch(API+"/api/predict/"+kind,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.detail||"Prediction failed");
 result.innerHTML=kind==="price"?`Estimated price: <strong>₹${d.estimated_price_per_kg}/kg</strong><br>Indicative range: ₹${d.indicative_low}–₹${d.indicative_high}/kg<br><small>${escapeHtml(d.note)}</small>`:`Demand level: <strong>${d.label}</strong><br>Demo demand index: ${d.estimated_demand_index}<br><small>${escapeHtml(d.note)}</small>`;
 }catch(e){result.textContent=e.message+". Is the backend running?"}
}
async function loadProducts(){
 const target=document.getElementById("products"), q=(document.getElementById("search").value||"").toLowerCase();
 try{const r=await fetch(API+"/api/products");const items=await r.json();const filtered=items.filter(p=>p.crop.toLowerCase().includes(q)||p.location.toLowerCase().includes(q));
 target.innerHTML=filtered.length?filtered.map(p=>`<article class="product"><div class="emoji">${cropEmoji[p.crop]||"🌿"}</div><h3>${escapeHtml(p.crop)}</h3><p>📍 ${escapeHtml(p.location)} · ${escapeHtml(p.farmer_name)}</p><p>${p.quantity} kg available</p><div class="price">₹${p.price}/kg</div><p>${escapeHtml(p.description||"Fresh farm produce")}</p></article>`).join(""):`<div class="empty">No listings yet. Farmers can add the first product below.</div>`;
 }catch(e){target.innerHTML='<div class="empty">Marketplace unavailable. Start the backend to load listings.</div>'}
}
async function addProduct(){
 const msg=document.getElementById("sellMessage");if(!user){msg.textContent="Please log in as a farmer first.";showAuth();return}if(user.role!=="farmer"){msg.textContent="Only farmer accounts can publish listings.";return}
 const body={farmer_id:user.id,crop:document.getElementById("sellCrop").value,quantity:Number(document.getElementById("sellQty").value),price:Number(document.getElementById("sellPrice").value),location:document.getElementById("sellLocation").value,description:document.getElementById("sellDesc").value};
 try{const r=await fetch(API+"/api/products",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.detail||"Could not publish");msg.textContent="Listing published successfully!";loadProducts()}catch(e){msg.textContent=e.message}
}
updateAuth();loadProducts();
