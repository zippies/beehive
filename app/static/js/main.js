$(function(){
    $("#helponenv").popover({html:true})
    $("#helponfile").popover({html:true})
    sessionStorage.clear()
    sessionStorage.choicedMachine = parseInt(0)
    sessionStorage.apicount = parseInt(1)
    getMachines();
    freshStatus();
    
    $("#clearbtn").click(clearResult)

    $("#startbtn").click(function(){
        if($("#startbtn").attr("disabled") != "disabled"){
            if(!validateForm()){
                return
            }
            $("#startbtn").attr("disabled","disabled")

            if(!localStorage.runningjob){

                clearResult();

                var formdata = new FormData($("#newmissionform")[0])
                $.ajax({
                    url:"/newmission",
                    type:"POST",
                    data:formdata,
                    dataType:"JSON",
                    cache:false,
                    processData:false,
                    contentType:false,
                    error:function(request){
                        layer.msg(request.status,{offset:"200px"})
                        localStorage.clear();
                    },
                    success:function(data){
                        if(data.result){
                            localStorage.runningjob = data.missionid;
                            sessionStorage.prejob = data.missionid
                            freshStatus()
                            console.log("fresh end")
                        }else{
                            $("#startbtn").removeAttr("disabled")
                            layer.msg("运行失败:"+data.errorMsg,{offset:"200px"})
                        }
                    }
                })
            }else{
                $("html,body").animate({scrollTop:$("#runtimeConfig").offset().top},1000)
            }
        }
    })


    $("#stopbtn").click(function(){
        if($("#stopbtn").attr("disabled") != "disabled"){
            $.ajax({
                    url:"/stopmission/"+localStorage.runningjob,
                    type:"post",
                    error:function(request){
                        layer.msg(request.status,{offset:"200px"})
                        console.log(request.status)
                    },
                    success:function(data){
                        if(data.result){
                            $("#startbtn").removeAttr("disabled")
                            $("#stopbtn").attr("disabled","disabled")
                            layer.msg("停止成功",{offset:"200px"})
                            console.log("停止成功")
                        }else{
                            layer.msg("停止失败:"+data.errorMsg,{offset:"200px"})
                            console.log("停止失败:"+data.errorMsg)
                        }
                    }
                })
        }
    })
})


function addenv(apiid){
    if(eval("sessionStorage.envcount_"+apiid+"")){
        eval("sessionStorage.envcount_"+apiid+" = parseInt(sessionStorage.envcount_"+apiid+") + 1")
    }else{
        eval("sessionStorage.envcount_"+apiid+" = 1")
    }
    envid = eval("sessionStorage.envcount_"+apiid+"")

    $("#envlist-"+apiid).append("<div id='env-"+apiid+"-"+envid+"'><input type='checkbox' name='env-"+apiid+"' style='display:none' checked='checked'>匹配自: <label><input type='radio' name='envsource-"+apiid+"-"+envid+"' value='header'> 响应头</label> <label><input type='radio' name='envsource-"+apiid+"-"+envid+"' value='body' checked='checked'> 响应体</label> <input type='text' placeholder='正则匹配表达式'  class='required' name='envregx-"+apiid+"-"+envid+"'> <input type='text' class='required' name='envname-"+apiid+"-"+envid+"' placeholder='将匹配值保存为变量名'> <a href='javascript:;' onclick='delenv("+apiid+","+envid+")'>删除</a></div>")
}

function delenv(apiid,envid){
    $("#env-"+apiid+"-"+envid).remove()
    eval("sessionStorage.envcount_"+apiid+" = parseInt(sessionStorage.envcount_"+apiid+") - 1")
}

function clearResult(){
    localStorage.clear()
    $("#elapsed").html(0)
    $("#looptime-state").html(0)
    $("#samples").html(0)
    $("#min-time").html(0)
    $("#max-time").html(0)
    $("#avg-time").html(0)
    $("#throught").html(0)
    $("#errors").html(0)
    $("#error-percent").html(0)
    $("#errordiv").empty()
    $("#elapsediv").empty()
    $("#progressdiv").hide()
    $("#initialdetail").hide()
    $("#runningstate").removeClass("btn-success").removeClass("btn-danger").addClass("btn-warning").html("未启动")
    $("#progressbar").removeClass("progress-bar-success").removeClass("progress-bar-danger").addClass("progress-bar-warning")
}

function freshStatus(){
    if(localStorage.runningjob){
        $("#initialdetail").show()
        $("html,body").animate({scrollTop:$("#runtimeConfig").offset().top},1000)
        var interval = window.setInterval(function(){
            $.ajax({
                url:"/freshstatus/"+localStorage.runningjob,
                type:"get",
                error:function(request){
                    layer.msg(request.status,{offset:"200px"})
                    window.clearInterval(interval)
                },
                success:function(data){
                    resp = JSON.parse(data)
                    if(resp.s == -1){
                        window.clearInterval(interval)
                        $("#startbtn").removeAttr("disabled")
                        $("#progressbar").removeClass("progress-bar-warning").addClass("progress-bar-danger");
                        $("#initialdetail").hide();
                        $("#runningstate").removeClass("btn-success").removeClass("btn-warning").addClass("btn-danger").html("启动失败");
                        layer.msg(resp.i,{offset:"200px"});
                        return
                    }
                    if(resp.s != 0){
                        showerror(resp)
                        if(resp.s  == 1){
                            if($("#progressdiv").is(":hidden")){
                                layer.msg("开始压测",{offset:"100px"}) 
                                $("#stopbtn").removeAttr("disabled")
                            }
                            $("#progressdiv").show()
                            $("#progressbar").removeClass("progress-bar-warning").addClass("progress-bar-danger").attr("aria-valuemax",resp.l).attr("data-transitiongoal",resp.p);
                            $("#runningstate").removeClass("btn-warning").removeClass("btn-success").addClass("btn-danger").html("正在压测");
                        }else{
                            console.log("finished here")
                            $("#startbtn").removeAttr("disabled")
                            $("#stopbtn").attr("disabled","disabled")
                            $("#progressbar").removeClass("progress-bar-warning").removeClass("progress-bar-danger").addClass("progress-bar-success").attr("aria-valuemax",resp.l).attr("data-transitiongoal",resp.p);
                            $("#runningstate").removeClass("btn-danger").removeClass("btn-warning").addClass("btn-success").html("压测完成");

                            var errorChart = echarts.init(document.getElementById('errordiv'));
                            var elapseChart = echarts.init(document.getElementById('elapsediv'));

                            $.ajax({
                                url:"/getErrorChart/"+localStorage.runningjob,
                                type:"get",
                                error:function(request){
                                    layer.msg(request.status,{offset:"200px"})
                                },
                                success:function(data){
                                    errorChart.setOption(data);
                                    errorChart.on('click', function (params) {
                                        showerrordetail(params.name);
                                    });
                                }
                            })

                            $.ajax({
                                url:"/getElapseChart/"+localStorage.runningjob,
                                type:"get",
                                error:function(request){
                                    layer.msg(request.status,{offset:"200px"})
                                },
                                success:function(data){
                                    elapseChart.setOption(data);
                                }
                            })

                            localStorage.clear();
                            window.clearInterval(interval);
                        }
                        $("#initialdetail").hide()
                        $('.progress .progress-bar').progressbar({display_text: 'center', use_percentage: false, amount_format: function(p, t) {return p + ' / ' + t;}});
                        $("#elapsed").html(resp.e)
                        $("#looptime-state").html(resp.l)
                        $("#samples").html(resp.sas)
                        $("#min-time").html(resp.min_e)
                        $("#max-time").html(resp.max_e)
                        $("#avg-time").html(resp.avg_e)
                        $("#throught").html(resp.toh)
                        $("#errors").html(resp.es)
                        $("#error-percent").html(resp.e_p)
                    }else{
                        $("#progressbar").attr("data-transitiongoal",resp.p);
                        $('.progress .progress-bar').progressbar({display_text: 'center', use_percentage: false, amount_format: function(p, t) {return p + ' / ' + t;}});
                        $("#initialstate").html(resp.i)
                        $("#runningstate").removeClass("btn-success").removeClass("btn-danger").addClass("btn-warning").html("初始化mission配置")
                    }
                }
            })
        },3000)
    }else{

    }
}

function showerrordetail(errortype){
    $.ajax({
        url:"/showerror/"+sessionStorage.prejob+"/"+errortype,
        type:"get",
        error:function(request){
            layer.msg(request.status,{offset:"200px"})
        },
        success:function(data){
            layer.open({
                type: 1,
                title: errortype,
                offset: "200px",
                area: [document.body.clientWidth * 0.8 +'px', '300px'], //宽高
                content: data
            });
        }
    })
}

function showerror(resp){
    if(resp.e_c && !sessionStorage.e_c){
        $("#connerror").show()
        $("#connectTimeout").html(resp.e_c)
    }
    if(resp.e_r && !sessionStorage.e_r){
        $("#resperror").show()
        $("#respTimeout").html(resp.e_r)
    }
    if(resp.e_a && !sessionStorage.e_a){
        $("#asserterror").show()
        $("#assertionError").html(resp.e_a)
    }
    if(resp.e_u && !sessionStorage.e_u){
        $("#unknownerror").show()
        $("#unknownError").html(resp.e_u)
    }
}

function testapi(apiid){
    if(!$.trim($("#url-"+apiid).val())){
        $("#url-"+apiid).focus();
        layer.msg("url不能为空",{offset:"200px"});
        return false;
    }
    layer.load(2,{offset:"400px"});

    var formdata = new FormData($("#newmissionform")[0])

    $.ajax({
        url:"/testapi/"+apiid,
        type:"POST",
        data:formdata,
        dataType:"JSON",
        cache:false,
        processData:false,
        contentType:false,
        error:function(request){
            layer.msg(request.status)
            layer.closeAll('loading');
        },
        success:function(data){
            layer.closeAll('loading');
            if(data.result){
                layer.open({
                    type: 1,
                    shadeClose: true,
                    title:"测试结果",
                    shade: false,
                    maxmin: true, //开启最大化最小化按钮
                    area: ['893px', '600px'],
                    offset:"200px",
                    content: data.message
                });
            }else{
                layer.msg("运行失败:"+data.errorMsg,{offset:"200px"})
            }
        }
    })
}


function validateForm(){
    var allpass = true;

    for(var i=1;i<=parseInt(sessionStorage.apicount);i++){
        if(!$.trim($("#url-"+i).val())){
            $("#apilist-"+i).click()
            $("#url-"+i).focus();
            layer.msg("url不能为空",{offset:"200px"});
            return false;
        }
    }

    $(".required").each(function(){
        if(!$(this).val()){
            $(this).focus();
            layer.msg("请填写该值",{offset:"200px"});
            allpass = false;
        }
    })

    if(allpass && parseInt(sessionStorage.choicedMachine) == 0){
        layer.msg("请选择执行机器",{offset:"200px"})
        return false;
    }

    return allpass;
}


function getMachines(){
    $.ajax({
        url:"/getmachines?source=0",
        type:"get",
        error:function(request){
            layer.msg("获取机器信息失败:"+request.status)
        },
        success:function(data){
            $("#machinelistdiv").append(data);
        }
    })
}


function showChange(id){
    if($("#machinediv_"+id).css("background-color") == 'rgba(0, 0, 0, 0)'){
        $("#machinediv_"+id).css("background-color","#87CEFF")
        sessionStorage.choicedMachine = parseInt(sessionStorage.choicedMachine) + 1
    }else{
        $("#machinediv_"+id).css("background-color","rgba(0, 0, 0, 0)")
        sessionStorage.choicedMachine = parseInt(sessionStorage.choicedMachine) - 1
    }
}


function addApi(){
    layer.load(2,{offset:"400px"});
    $("#apilist > a").removeClass("active")
    sessionStorage.apicount = parseInt(sessionStorage.apicount) + 1
    $("#apilist").append('<a href="javascript:;" id="apilist-'+sessionStorage.apicount+'" class="list-group-item active" onclick="showapiconfig('+sessionStorage.apicount+')">接口_'+sessionStorage.apicount+'</a>')
    $.ajax({
        url:"/getapitemplate/" + sessionStorage.apicount,
        type:"get",
        error:function(request){
            layer.msg(request.status)
            layer.closeAll('loading');
        },
        success:function(data){
            $(".apilistitem").hide()
            $("#apilistdiv").append(data)
            layer.closeAll('loading');
        }
    })
}


function showapiconfig(apiid){
    $("#apilist > a").removeClass("active")
    $("#apilist-"+apiid).addClass("active")
    $(".apilistitem").hide()
    $("#apilistDetail-"+apiid).show()
}


function delapi(apiid){
    if(parseInt(sessionStorage.apicount) == 1){
        layer.msg("至少需要保留一个接口",{offset:"200px"})
        return
    }
    $("#apilist-"+apiid).remove()
    $("#apilistDetail-"+apiid).remove()
    sessionStorage.apicount = parseInt(sessionStorage.apicount) - 1
    $("#apilist-1").click()
}